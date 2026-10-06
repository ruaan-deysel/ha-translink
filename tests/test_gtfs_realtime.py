"""Comprehensive unit tests for pure-Python GTFS-RT Protobuf decoder."""

from __future__ import annotations

import struct
from typing import Any

from custom_components.translink.api.gtfs_realtime import (
    _decode_string,
    _decode_translated_string,
    _parse_fields,
    _parse_varint,
    parse_alerts,
    parse_trip_updates,
    parse_vehicle_positions,
)


def _encode_varint(val: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    if val < 0:
        val += 1 << 64
    res = bytearray()
    while True:
        b = val & 0x7F
        val >>= 7
        if val:
            res.append(b | 0x80)
        else:
            res.append(b)
            break
    return bytes(res)


def _encode_field(field_num: int, wire_type: int, data: Any) -> bytes:
    """Encode a protobuf field."""
    tag = (field_num << 3) | wire_type
    header = _encode_varint(tag)
    if wire_type == 0:
        return header + _encode_varint(int(data))
    if wire_type == 1:
        return header + struct.pack("<Q", int(data))
    if wire_type == 2:
        raw = (
            bytes(data)
            if isinstance(data, (bytes, bytearray))
            else str(data).encode("utf-8")
        )
        return header + _encode_varint(len(raw)) + raw
    if wire_type == 5:
        return header + struct.pack("<f", float(data))
    return header


def test_varint_multibyte() -> None:
    """Test varint decoding across multiple bytes."""
    encoded = _encode_varint(16384)
    val, offset = _parse_varint(encoded, 0)
    assert val == 16384
    assert offset == len(encoded)


def test_parse_fields_all_wire_types() -> None:
    """Test _parse_fields handles wire types 0, 1, 2, 5 and breaks on unsupported types."""
    payload = (
        _encode_field(1, 0, 42)  # Varint
        + _encode_field(2, 1, 1000000)  # 64-bit
        + _encode_field(3, 2, b"hello")  # Length-delimited
        + _encode_field(4, 5, 3.14)  # 32-bit float
        + _encode_field(5, 7, 0)  # Unsupported wire type (should break)
    )

    fields = _parse_fields(payload, limit=len(payload))
    assert len(fields) == 4
    assert fields[0] == (1, 0, 42)
    assert fields[1] == (2, 1, 1000000)
    assert fields[2] == (3, 2, b"hello")
    assert fields[3][0] == 4
    assert fields[3][1] == 5
    assert round(fields[3][2], 2) == 3.14


def test_decode_string_variants() -> None:
    """Test _decode_string with bytes, str, and integer."""
    assert _decode_string(b"translink") == "translink"
    assert _decode_string(b"\xff\xfe") == "\ufffd\ufffd"
    assert _decode_string("already_string") == "already_string"
    assert _decode_string(12345) == "12345"


def test_decode_translated_string() -> None:
    """Test _decode_translated_string extracts text or returns empty string."""
    # Empty message
    assert _decode_translated_string(b"") == ""

    # Message with translation (field 1) containing text (field 1)
    trans_sub = _encode_field(1, 2, "Platform 2 closed")
    trans_msg = _encode_field(1, 2, trans_sub)
    assert _decode_translated_string(trans_msg) == "Platform 2 closed"

    # Message with other fields
    other_msg = _encode_field(2, 2, b"other")
    assert _decode_translated_string(other_msg) == ""


def test_parse_alerts_comprehensive() -> None:
    """Test parse_alerts with full alert, description-only alert, and ignored records."""
    # Build Entity 1: Full alert with header, description, route, and stop selectors
    es_msg = _encode_field(2, 2, "ROUTE_66") + _encode_field(3, 2, "STOP_100")
    header_sub = _encode_field(1, 2, _encode_field(1, 2, "Delays on Route 66"))
    desc_sub = _encode_field(1, 2, _encode_field(1, 2, "Heavy traffic congestion"))

    alert_body_1 = (
        _encode_field(5, 2, es_msg)
        + _encode_field(10, 2, header_sub)
        + _encode_field(11, 2, desc_sub)
    )

    entity_1 = _encode_field(1, 2, "ENT_ALERT_1") + _encode_field(5, 2, alert_body_1)

    # Build Entity 2: Description-only alert (header defaults to truncated desc)
    desc_sub_2 = _encode_field(1, 2, _encode_field(1, 2, "Short alert message"))
    alert_body_2 = _encode_field(11, 2, desc_sub_2)
    entity_2 = _encode_field(1, 2, "ENT_ALERT_2") + _encode_field(5, 2, alert_body_2)

    # Build Entity 3: Entity without alert bytes (should be ignored)
    entity_3 = _encode_field(1, 2, "ENT_ALERT_3")

    # Build non-entity field (field 1 header)
    top_header = _encode_field(1, 2, b"gtfs_header")

    feed = (
        top_header
        + _encode_field(2, 2, entity_1)
        + _encode_field(2, 2, entity_2)
        + _encode_field(2, 2, entity_3)
    )

    alerts = parse_alerts(feed)
    assert len(alerts) == 2

    assert alerts[0].entity_id == "ENT_ALERT_1"
    assert alerts[0].header_text == "Delays on Route 66"
    assert alerts[0].description_text == "Heavy traffic congestion"
    assert alerts[0].route_ids == ("ROUTE_66",)
    assert alerts[0].stop_ids == ("STOP_100",)

    assert alerts[1].entity_id == "ENT_ALERT_2"
    assert alerts[1].header_text == "Short alert message"
    assert alerts[1].description_text == "Short alert message"


def test_parse_trip_updates_negative_delay_and_fields() -> None:
    """Test parse_trip_updates with negative delay, timestamps, and stop updates."""
    # Stop time update with negative delay (-60 seconds as two's complement uint32)
    neg_delay_uint32 = 0x100000000 - 60
    stu_event = _encode_field(1, 0, neg_delay_uint32)  # delay
    stu = _encode_field(2, 2, stu_event) + _encode_field(4, 2, "STOP_TARGET")

    trip_desc = _encode_field(1, 2, "TRIP_NEG") + _encode_field(5, 2, "ROUTE_NEG")

    tu_body = (
        _encode_field(1, 2, trip_desc)
        + _encode_field(2, 2, stu)
        + _encode_field(4, 0, 1728180000)  # timestamp
        + _encode_field(5, 0, neg_delay_uint32)  # top-level delay
    )

    # Valid entity and an empty entity (no trip update body)
    entity_valid = _encode_field(1, 2, "ENT_TU_1") + _encode_field(3, 2, tu_body)
    entity_empty = _encode_field(1, 2, "ENT_TU_EMPTY")
    feed = (
        _encode_field(1, 2, b"header")
        + _encode_field(2, 2, entity_valid)
        + _encode_field(2, 2, entity_empty)
    )

    tu_map = parse_trip_updates(feed)
    assert "TRIP_NEG" in tu_map
    rec = tu_map["TRIP_NEG"]
    assert rec.delay_seconds == -60
    assert rec.stop_id == "STOP_TARGET"
    assert rec.timestamp == 1728180000
    assert rec.route_id == "ROUTE_NEG"


def test_parse_vehicle_positions_custom_fields() -> None:
    """Test parse_vehicle_positions with missing trip_id, vehicle entity without position, etc."""
    # Vehicle position without trip descriptor, only vehicle descriptor and position
    veh_desc = _encode_field(1, 2, "VEH_999") + _encode_field(2, 2, "Plate 999")
    pos_desc = (
        _encode_field(1, 5, -27.47)  # lat
        + _encode_field(2, 5, 153.02)  # lon
        + _encode_field(3, 5, 45.0)  # bearing
        + _encode_field(5, 5, 20.0)  # speed
    )

    # Trip descriptor for vehicle position
    trip_desc = _encode_field(1, 2, "TRIP_VP_1") + _encode_field(5, 2, "ROUTE_VP_1")

    vp_body = (
        _encode_field(1, 2, trip_desc)
        + _encode_field(2, 2, pos_desc)
        + _encode_field(8, 2, veh_desc)
        + _encode_field(5, 0, 1728180000)  # timestamp
    )

    entity_valid = _encode_field(1, 2, "ENT_VP_1") + _encode_field(4, 2, vp_body)
    entity_no_pos = _encode_field(1, 2, "ENT_NO_POS") + _encode_field(
        4, 2, _encode_field(1, 2, trip_desc)
    )
    entity_empty = _encode_field(1, 2, "ENT_EMPTY")
    feed = (
        _encode_field(1, 2, b"header")
        + _encode_field(2, 2, entity_valid)
        + _encode_field(2, 2, entity_no_pos)
        + _encode_field(2, 2, entity_empty)
    )

    vp_map = parse_vehicle_positions(feed)
    assert "TRIP_VP_1" in vp_map
    rec = vp_map["TRIP_VP_1"]
    assert rec.trip_id == "TRIP_VP_1"
    assert rec.route_id == "ROUTE_VP_1"
    assert rec.vehicle_id == "VEH_999"
    assert rec.vehicle_label == "Plate 999"
    assert round(rec.latitude, 2) == -27.47
    assert round(rec.longitude, 2) == 153.02
    assert rec.bearing == 45.0
    assert rec.speed == 20.0
    assert rec.timestamp == 1728180000


def test_gtfs_varint_truncated() -> None:
    """Test varint loop terminates if bytes end before 0x80 bit is cleared."""
    _, offset = _parse_varint(b"\x80\x80", 0)
    assert offset == 2


def test_gtfs_realtime_extra_and_unknown_fields() -> None:
    """Test all fallback branches with unknown fields and missing identifiers."""
    # 1. TranslatedString with language field (t_num == 2) and no text field
    trans_with_lang = _encode_field(1, 2, _encode_field(2, 2, "en"))
    assert _decode_translated_string(trans_with_lang) == ""

    # 2. VehiclePosition with no trip_id and no veh_id, but extra unknown fields (99)
    pos_desc = (
        _encode_field(1, 5, -27.47)
        + _encode_field(2, 5, 153.02)
        + _encode_field(4, 0, 12345)  # pf_num == 4 (odometer / unhandled)
        + _encode_field(99, 0, 1)
    )
    vp_body = (
        _encode_field(2, 2, pos_desc)
        + _encode_field(1, 2, _encode_field(99, 0, 1))  # TripDesc unknown field
        + _encode_field(8, 2, _encode_field(99, 0, 1))  # VehDesc unknown field
        + _encode_field(99, 0, 1)  # VP body unknown field
    )
    entity_unknown = (
        _encode_field(1, 2, "ENT_NO_TRIP_NO_VEH")
        + _encode_field(4, 2, vp_body)
        + _encode_field(99, 0, 1)  # Entity unknown field
    )
    feed_vp = _encode_field(2, 2, entity_unknown)
    res_vp = parse_vehicle_positions(feed_vp)
    assert "ENT_NO_TRIP_NO_VEH" in res_vp

    # 3. TripUpdate with no trip_id and extra unknown fields (99)
    stu = (
        _encode_field(2, 2, _encode_field(2, 0, 100))  # StopTimeEvent unknown field 2
        + _encode_field(99, 0, 1)  # STU unknown field
    )
    tu_body = (
        _encode_field(1, 2, _encode_field(99, 0, 1))  # TripDesc unknown field
        + _encode_field(2, 2, stu)
        + _encode_field(99, 0, 1)  # TU unknown field
    )
    entity_tu = (
        _encode_field(1, 2, "ENT_TU_NO_TRIP")
        + _encode_field(3, 2, tu_body)
        + _encode_field(99, 0, 1)
    )
    feed_tu = _encode_field(2, 2, entity_tu)
    res_tu = parse_trip_updates(feed_tu)
    assert "ENT_TU_NO_TRIP" in res_tu

    # 4. Alert with unknown fields and alert with neither header nor description
    alert_empty = (
        _encode_field(5, 2, _encode_field(99, 0, 1))  # Selector unknown field
        + _encode_field(99, 0, 1)  # Alert unknown field
    )
    entity_alert_empty = (
        _encode_field(1, 2, "ENT_ALERT_EMPTY")
        + _encode_field(5, 2, alert_empty)
        + _encode_field(99, 0, 1)
    )
    feed_alert = _encode_field(2, 2, entity_alert_empty)
    assert parse_alerts(feed_alert) == []
