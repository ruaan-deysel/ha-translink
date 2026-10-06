"""Tests for Translink sensor platform."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from custom_components.translink.client import JourneySummary, StopSummary
from custom_components.translink.const import (
    CONF_MODE,
    CONF_NAME,
    DOMAIN,
    MODE_JOURNEY,
    MODE_STOP,
)
from custom_components.translink.sensor import (
    JOURNEY_SENSORS,
    STOP_SENSORS,
    TranslinkSensor,
    async_setup_entry,
)


class FakeEntry:
    """Fake ConfigEntry for testing."""

    def __init__(self, mode: str = MODE_JOURNEY) -> None:
        self.entry_id = "test_entry_id"
        self.data = {
            CONF_MODE: mode,
            CONF_NAME: "My Journey",
        }
        self.runtime_data = None


class FakeCoordinator:
    """Fake coordinator for sensor tests."""

    def __init__(self, mode: str = MODE_JOURNEY, data: Any = None) -> None:
        self.mode = mode
        self.data = data
        self.entry = FakeEntry(mode=mode)
        self._listeners: list[Any] = []

    def async_add_listener(self, update_callback: Any) -> Any:
        self._listeners.append(update_callback)
        return lambda: self._listeners.remove(update_callback)


@pytest.fixture
def sample_journey_summary() -> JourneySummary:
    """Fixture with a populated JourneySummary."""
    dep_time = datetime(2026, 10, 6, 9, 30, tzinfo=UTC)
    arr_time = datetime(2026, 10, 6, 10, 11, tzinfo=UTC)
    return JourneySummary(
        status="on_time",
        departure_time=dep_time,
        arrival_time=arr_time,
        duration_mins=41,
        transfers=0,
        next_service_name="T2 Springfield Central",
        next_service_vehicle="Train",
        next_service_headsign="Springfield Central",
        origin_name="Central station",
        origin_platform="5",
        destination_name="Springfield Central station",
        destination_platform="1",
        fare_price=0.5,
        fare_currency="AUD",
        fare_type="Adult",
        walking_distance_m=120,
        delay_mins=1,
        disruptions_count=0,
        itinerary_legs=[{"travelMode": "Train", "durationMins": 41}],
    )


@pytest.fixture
def sample_stop_summary() -> StopSummary:
    """Fixture with a populated StopSummary."""
    dep_time = datetime(2026, 10, 6, 9, 35, tzinfo=UTC)
    return StopSummary(
        stop_id="ST:place_romsta",
        stop_name="Roma Street",
        next_departure_time=dep_time,
        next_route="T1 Caboolture",
        next_vehicle="Train",
        next_platform="3",
        delay_mins=2,
        departures=[{"route": "T1"}],
        disruptions_count=1,
    )


@pytest.mark.asyncio
async def test_async_setup_entry_journey(
    sample_journey_summary: JourneySummary,
) -> None:
    """Test setting up journey sensors."""
    hass = MagicMock()
    entry = FakeEntry(mode=MODE_JOURNEY)
    coordinator = FakeCoordinator(mode=MODE_JOURNEY, data=sample_journey_summary)
    entry.runtime_data = coordinator  # type: ignore[assignment]
    hass.data = {DOMAIN: {entry.entry_id: coordinator}}

    entities: list[TranslinkSensor] = []
    await async_setup_entry(hass, entry, lambda added: entities.extend(added))  # type: ignore[arg-type]

    assert len(entities) == len(JOURNEY_SENSORS)
    assert any(e.entity_description.key == "next_departure" for e in entities)
    assert any(e.entity_description.key == "duration" for e in entities)
    assert any(e.entity_description.key == "status" for e in entities)


@pytest.mark.asyncio
async def test_async_setup_entry_stop(sample_stop_summary: StopSummary) -> None:
    """Test setting up stop sensors."""
    hass = MagicMock()
    entry = FakeEntry(mode=MODE_STOP)
    coordinator = FakeCoordinator(mode=MODE_STOP, data=sample_stop_summary)
    entry.runtime_data = coordinator  # type: ignore[assignment]
    hass.data = {DOMAIN: {entry.entry_id: coordinator}}

    entities: list[TranslinkSensor] = []
    await async_setup_entry(hass, entry, lambda added: entities.extend(added))  # type: ignore[arg-type]

    assert len(entities) == len(STOP_SENSORS)


def test_journey_sensor_properties(sample_journey_summary: JourneySummary) -> None:
    """Test values and attributes for journey sensors."""
    coordinator = FakeCoordinator(mode=MODE_JOURNEY, data=sample_journey_summary)
    entry = FakeEntry(mode=MODE_JOURNEY)

    sensors = {
        desc.key: TranslinkSensor(coordinator, desc, entry)  # type: ignore[arg-type]
        for desc in JOURNEY_SENSORS
    }

    assert sensors["duration"].native_value == 41
    assert sensors["status"].native_value == "on_time"
    assert sensors["next_service"].native_value == "T2 Springfield Central (Train)"
    assert sensors["platform"].native_value == "5"
    assert sensors["transfers"].native_value == 0
    assert sensors["fare"].native_value == 0.5
    assert sensors["delay"].native_value == 1
    assert sensors["walking_distance"].native_value == 120
    assert sensors["disruptions"].native_value == 0
    assert sensors["disruption_description"].native_value == "Normal"

    # Extra state attributes
    disruption_attrs = sensors["disruptions"].extra_state_attributes
    assert disruption_attrs["summary"] == "Normal"
    assert disruption_attrs["description"] == "No active disruptions"
    assert disruption_attrs["latest_title"] is None

    desc_attrs = sensors["disruption_description"].extra_state_attributes
    assert desc_attrs["count"] == 0
    assert desc_attrs["description"] == "No active disruptions"

    # Extra state attributes
    attrs = sensors["next_departure"].extra_state_attributes
    assert attrs["platform"] == "5"
    assert attrs["origin"] == "Central station"
    assert attrs["readable_time"] == "07:30 PM"

    arrival_attrs = sensors["arrival_time"].extra_state_attributes
    assert arrival_attrs["readable_time"] == "08:11 PM"

    # Test None departure_time produces None readable_time
    sample_journey_summary.departure_time = None
    attrs_none = sensors["next_departure"].extra_state_attributes
    assert attrs_none["readable_time"] is None


def test_stop_sensor_properties(sample_stop_summary: StopSummary) -> None:
    """Test values and attributes for stop departure sensors."""
    sample_stop_summary.disruptions_count = 1
    sample_stop_summary.disruptions = [
        {"id": 1, "title": "Lift Maintenance", "description": "Platform 3 lift closed."}
    ]
    sample_stop_summary.disruptions_summary = "Lift Maintenance"
    sample_stop_summary.disruptions_description = (
        "• Lift Maintenance: Platform 3 lift closed."
    )
    sample_stop_summary.latest_disruption_title = "Lift Maintenance"
    sample_stop_summary.latest_disruption_description = "Platform 3 lift closed."

    coordinator = FakeCoordinator(mode=MODE_STOP, data=sample_stop_summary)
    entry = FakeEntry(mode=MODE_STOP)

    sensors = {
        desc.key: TranslinkSensor(coordinator, desc, entry)  # type: ignore[arg-type]
        for desc in STOP_SENSORS
    }

    assert sensors["disruptions"].native_value == 1
    assert sensors["disruption_description"].native_value == "Lift Maintenance"

    disruption_attrs = sensors["disruptions"].extra_state_attributes
    assert disruption_attrs["summary"] == "Lift Maintenance"
    assert (
        disruption_attrs["description"] == "• Lift Maintenance: Platform 3 lift closed."
    )
    assert disruption_attrs["latest_title"] == "Lift Maintenance"

    desc_attrs = sensors["disruption_description"].extra_state_attributes
    assert desc_attrs["count"] == 1
    assert desc_attrs["description"] == "• Lift Maintenance: Platform 3 lift closed."


def test_sensor_fallback_disruption_description() -> None:
    """Test disruption_description sensor fallback when count > 0 but no title."""
    summary = JourneySummary(
        disruptions_count=1,
        disruptions=[{"id": 99}],
        latest_disruption_title=None,
    )
    coordinator = FakeCoordinator(mode=MODE_JOURNEY, data=summary)
    entry = FakeEntry(mode=MODE_JOURNEY)

    sensors = {
        desc.key: TranslinkSensor(coordinator, desc, entry)  # type: ignore[arg-type]
        for desc in JOURNEY_SENSORS
    }
    assert sensors["disruption_description"].native_value == "Service Disruption"


def test_sensor_none_data() -> None:
    """Test sensor behavior when coordinator data is None."""
    coordinator = FakeCoordinator(mode=MODE_JOURNEY, data=None)
    entry = FakeEntry(mode=MODE_JOURNEY)
    sensor = TranslinkSensor(coordinator, JOURNEY_SENSORS[0], entry)  # type: ignore[arg-type]

    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}
