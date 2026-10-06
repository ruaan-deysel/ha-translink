"""Unit tests for Translink API client, Protobuf parser, and models."""

from __future__ import annotations

from datetime import UTC
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.translink.api.gtfs_realtime import (
    TripUpdateRecord,
    VehiclePositionRecord,
    _parse_fields,
    _parse_varint,
)
from custom_components.translink.client import (
    JourneyPlanResult,
    JourneySummary,
    TranslinkClient,
    TranslinkResponseError,
    build_journey_summary,
    calculate_plan_hash,
    parse_alerts,
    parse_iso_datetime,
    parse_trip_updates,
    parse_vehicle_positions,
    redact_sensitive,
)


def test_calculate_plan_hash() -> None:
    """Test 32-bit signed string hash computation."""
    assert calculate_plan_hash("") == 0
    h1 = calculate_plan_hash("searchDate=2026-10-06&searchTime=9%3A30am")
    assert isinstance(h1, int)
    assert -0x80000000 <= h1 <= 0x7FFFFFFF


def test_parse_iso_datetime() -> None:
    """Test ISO timestamp parsing."""
    assert parse_iso_datetime(None) is None
    assert parse_iso_datetime("") is None
    assert parse_iso_datetime("invalid") is None

    parsed = parse_iso_datetime("2026-10-06T00:24:00Z")
    assert parsed is not None
    assert parsed.year == 2026
    assert parsed.month == 10
    assert parsed.day == 6
    assert parsed.hour == 0
    assert parsed.minute == 24
    assert parsed.tzinfo == UTC


def test_varint_and_fields_parser() -> None:
    """Test low level varint and fields parsing."""
    val, offset = _parse_varint(b"\x01", 0)
    assert val == 1
    assert offset == 1

    # Multiple bytes varint (300 = 0xac 0x02)
    val, offset = _parse_varint(b"\xac\x02", 0)
    assert val == 300
    assert offset == 2

    fields = _parse_fields(b"")
    assert fields == []


def test_parse_vehicle_positions(sample_vehicle_positions_bytes: bytes) -> None:
    """Test parsing GTFS-RT VehiclePositions payload."""
    vp_map = parse_vehicle_positions(sample_vehicle_positions_bytes)
    assert len(vp_map) > 0

    sample_record = next(iter(vp_map.values()))
    assert isinstance(sample_record, VehiclePositionRecord)
    assert sample_record.latitude != 0.0
    assert sample_record.longitude != 0.0
    assert -90.0 <= sample_record.latitude <= 90.0
    assert -180.0 <= sample_record.longitude <= 180.0


def test_parse_trip_updates(sample_trip_updates_bytes: bytes) -> None:
    """Test parsing GTFS-RT TripUpdates payload."""
    tu_map = parse_trip_updates(sample_trip_updates_bytes)
    assert len(tu_map) > 0

    sample_record = next(iter(tu_map.values()))
    assert isinstance(sample_record, TripUpdateRecord)
    assert isinstance(sample_record.delay_seconds, int)


def test_parse_alerts() -> None:
    """Test alerts parser with empty or truncated bytes."""
    alerts = parse_alerts(b"")
    assert alerts == []


def test_build_journey_summary_with_plan(
    plan_response_data: dict[str, Any],
    sample_vehicle_positions_bytes: bytes,
    sample_trip_updates_bytes: bytes,
) -> None:
    """Test build_journey_summary with valid plan fixture and feeds."""
    plan = JourneyPlanResult.model_validate(plan_response_data)
    vp_map = parse_vehicle_positions(sample_vehicle_positions_bytes)
    tu_map = parse_trip_updates(sample_trip_updates_bytes)

    # Test Adult fare preference
    summary = build_journey_summary(
        plan=plan,
        vehicle_positions=vp_map,
        trip_updates=tu_map,
        fare_preference="Adult",
        origin_name_fallback="Central",
        destination_name_fallback="Springfield Central",
    )

    assert isinstance(summary, JourneySummary)
    assert summary.status in ["scheduled", "on_time", "delayed", "departed", "arrived"]
    assert summary.departure_time is not None
    assert summary.arrival_time is not None
    assert summary.duration_mins == 41
    assert summary.transfers == 0
    assert summary.next_service_name == "T2 Springfield Central"
    assert summary.next_service_vehicle == "Train"
    assert summary.origin_platform == "5"
    assert summary.destination_platform == "1"
    assert summary.fare_price == 0.5
    assert summary.fare_currency == "AUD"
    assert len(summary.itinerary_legs) >= 1

    # Test Concession fare preference
    summary_concession = build_journey_summary(
        plan=plan,
        fare_preference="Concession",
    )
    assert summary_concession.fare_price == 0.5


def test_build_journey_summary_empty() -> None:
    """Test build_journey_summary when no itineraries are returned."""
    plan = JourneyPlanResult(itineraries=[])
    summary = build_journey_summary(
        plan=plan,
        origin_name_fallback="Origin",
        destination_name_fallback="Destination",
    )
    assert summary.status == "no_service"
    assert summary.origin_name == "Origin"
    assert summary.destination_name == "Destination"
    assert summary.duration_mins == 0


def test_redact_sensitive() -> None:
    """Test redaction helper."""
    assert redact_sensitive("abc") == "abc"
    assert redact_sensitive([1, 2, {"k": "v"}]) == [1, 2, {"k": "v"}]


@pytest.mark.asyncio
async def test_search_locations_success() -> None:
    """Test searching locations with successful mock response."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value=[
            {
                "LocationId": "ST:place_censta",
                "Description": "Central station, Brisbane City",
            }
        ]
    )

    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_session.closed = False

    client = TranslinkClient(session=mock_session)
    results = await client.search_locations("Central")

    assert len(results) == 1
    assert results[0].LocationId == "ST:place_censta"
    assert results[0].Description == "Central station, Brisbane City"

    # Query too short
    empty = await client.search_locations("a")
    assert empty == []


@pytest.mark.asyncio
async def test_search_locations_error() -> None:
    """Test searching locations error handling."""
    mock_response = MagicMock()
    mock_response.status = 500
    mock_response.text = AsyncMock(return_value="Server error")

    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_session.closed = False

    client = TranslinkClient(session=mock_session)
    with pytest.raises(TranslinkResponseError):
        await client.search_locations("Central")


@pytest.mark.asyncio
async def test_plan_journey_success(plan_response_data: dict[str, Any]) -> None:
    """Test plan_journey with mock response."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=plan_response_data)

    mock_session = MagicMock()
    mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_session.post.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_session.closed = False

    client = TranslinkClient(session=mock_session)
    plan = await client.plan_journey(
        start_location_id="ST:place_censta",
        start_name="Central station",
        end_location_id="ST:place_spcsta",
        end_name="Springfield Central",
    )

    assert len(plan.itineraries) == 2
    assert plan.itineraries[0].durationMins == 41


@pytest.mark.asyncio
async def test_get_stops_by_geolocation() -> None:
    """Test get_stops_by_geolocation with mock response."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(
        return_value=[{"id": "SI:123", "description": "Stop 1"}]
    )

    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_session.closed = False

    client = TranslinkClient(session=mock_session)
    stops = await client.get_stops_by_geolocation(-27.46, 153.02)
    assert len(stops) == 1
    assert stops[0]["id"] == "SI:123"


@pytest.mark.asyncio
async def test_client_close() -> None:
    """Test client close behaviour."""
    mock_session = MagicMock()
    mock_session.closed = False
    mock_session.close = AsyncMock()

    client = TranslinkClient()
    client._session = mock_session
    client._owns_session = True
    await client.close()
    mock_session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_vehicle_positions(sample_vehicle_positions_bytes: bytes) -> None:
    """Test fetch_vehicle_positions with mock HTTP response."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read = AsyncMock(return_value=sample_vehicle_positions_bytes)

    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_session.closed = False

    client = TranslinkClient(session=mock_session)
    vp = await client.fetch_vehicle_positions()
    assert len(vp) > 0


@pytest.mark.asyncio
async def test_fetch_trip_updates(sample_trip_updates_bytes: bytes) -> None:
    """Test fetch_trip_updates with mock HTTP response."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read = AsyncMock(return_value=sample_trip_updates_bytes)

    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_session.closed = False

    client = TranslinkClient(session=mock_session)
    tu = await client.fetch_trip_updates()
    assert len(tu) > 0


@pytest.mark.asyncio
async def test_fetch_alerts() -> None:
    """Test fetch_alerts with mock HTTP response."""
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read = AsyncMock(return_value=b"")

    mock_session = MagicMock()
    mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
    mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_session.closed = False

    client = TranslinkClient(session=mock_session)
    alerts = await client.fetch_alerts()
    assert alerts == []


def test_build_journey_summary_with_delay_and_vehicle(
    plan_response_data: dict[str, Any],
) -> None:
    """Test build_journey_summary with correlated trip update and vehicle position."""
    from datetime import datetime, timedelta

    from custom_components.translink.api.gtfs_realtime import (
        TripUpdateRecord,
        VehiclePositionRecord,
    )

    plan = JourneyPlanResult.model_validate(plan_response_data)
    first_trip_id = plan.itineraries[0].legs[0].tripId
    assert first_trip_id is not None

    trip_updates = {
        first_trip_id: TripUpdateRecord(
            entity_id="tu_1",
            trip_id=first_trip_id,
            route_id="RPSP",
            delay_seconds=300,
        )
    }
    vehicle_positions = {
        first_trip_id: VehiclePositionRecord(
            entity_id="vp_1",
            vehicle_id="VEH_42",
            vehicle_label="42",
            trip_id=first_trip_id,
            route_id="RPSP",
            latitude=-27.465,
            longitude=153.028,
            bearing=180.0,
            speed=15.0,
        )
    }

    # Test future departure with delay -> status "delayed"
    future_now = datetime(2026, 10, 5, 23, 0, 0, tzinfo=UTC)
    summary = build_journey_summary(
        plan,
        trip_updates=trip_updates,
        vehicle_positions=vehicle_positions,
        now=future_now,
    )
    assert summary.delay_mins == 5
    assert summary.status == "delayed"
    assert summary.vehicle_id == "VEH_42"
    assert summary.vehicle_latitude == -27.465
    assert summary.vehicle_bearing == 180.0
    assert summary.vehicle_speed == 15.0
    assert summary.vehicle_tracked is True

    # Test departed status
    dep_time = summary.departure_time
    arr_time = summary.arrival_time
    assert dep_time is not None and arr_time is not None
    mid_now = dep_time + timedelta(minutes=5)
    summary_departed = build_journey_summary(plan, now=mid_now)
    assert summary_departed.status == "departed"

    # Test arrived status
    after_arr_now = arr_time + timedelta(minutes=5)
    summary_arrived = build_journey_summary(plan, now=after_arr_now)
    assert summary_arrived.status == "arrived"
