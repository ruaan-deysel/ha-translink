"""Tests for Translink coordinator."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.translink.client import (
    JourneyPlanResult,
    JourneySummary,
    StopSummary,
    TranslinkConnectionError,
)
from custom_components.translink.const import (
    CONF_END_LOCATION_ID,
    CONF_END_NAME,
    CONF_MODE,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_START_LOCATION_ID,
    CONF_START_NAME,
    CONF_STOP_LOCATION_ID,
    CONF_STOP_NAME,
    DOMAIN,
    MODE_JOURNEY,
    MODE_STOP,
)
from custom_components.translink.coordinator import TranslinkCoordinator


@pytest.fixture
def journey_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Fixture for a journey config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_journey_1",
        data={
            CONF_MODE: MODE_JOURNEY,
            CONF_NAME: "Commute",
            CONF_START_LOCATION_ID: "ST:place_censta",
            CONF_START_NAME: "Central station",
            CONF_END_LOCATION_ID: "ST:place_spcsta",
            CONF_END_NAME: "Springfield Central",
            CONF_SCAN_INTERVAL: 60,
        },
        options={},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def stop_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Fixture for a stop config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id="entry_stop_1",
        data={
            CONF_MODE: MODE_STOP,
            CONF_NAME: "Roma Street",
            CONF_STOP_LOCATION_ID: "ST:place_romsta",
            CONF_STOP_NAME: "Roma Street station",
            CONF_SCAN_INTERVAL: 90,
        },
        options={},
    )
    entry.add_to_hass(hass)
    return entry


async def test_coordinator_init_journey(
    hass: HomeAssistant, journey_entry: MockConfigEntry
) -> None:
    """Test coordinator initialization for Journey mode."""
    with patch("custom_components.translink.coordinator.async_get_clientsession"):
        coordinator = TranslinkCoordinator(hass, journey_entry)

    assert coordinator.mode == MODE_JOURNEY
    assert coordinator.start_location_id == "ST:place_censta"
    assert coordinator.end_location_id == "ST:place_spcsta"
    assert coordinator.update_interval == timedelta(seconds=60)
    assert coordinator.track_vehicle is True


async def test_coordinator_init_stop(
    hass: HomeAssistant, stop_entry: MockConfigEntry
) -> None:
    """Test coordinator initialization for Stop mode."""
    with patch("custom_components.translink.coordinator.async_get_clientsession"):
        coordinator = TranslinkCoordinator(hass, stop_entry)

    assert coordinator.mode == MODE_STOP
    assert coordinator.update_interval == timedelta(seconds=90)


async def test_coordinator_update_journey_success(
    hass: HomeAssistant,
    journey_entry: MockConfigEntry,
    plan_response_data: dict[str, Any],
) -> None:
    """Test coordinator _async_update_journey successfully parses and caches data."""
    plan_result = JourneyPlanResult.model_validate(plan_response_data)

    with patch("custom_components.translink.coordinator.async_get_clientsession"):
        coordinator = TranslinkCoordinator(hass, journey_entry)

    coordinator.client.plan_journey = AsyncMock(return_value=plan_result)
    coordinator.client.fetch_vehicle_positions = AsyncMock(return_value={})
    coordinator.client.fetch_trip_updates = AsyncMock(return_value={})
    coordinator._store.async_save = AsyncMock()

    summary = await coordinator._async_update_data()
    assert isinstance(summary, JourneySummary)
    assert summary.status in ["scheduled", "on_time", "delayed", "departed", "arrived"]
    assert summary.duration_mins == 41
    assert coordinator._cached_summary == summary


async def test_coordinator_update_stop_success(
    hass: HomeAssistant,
    stop_entry: MockConfigEntry,
    plan_response_data: dict[str, Any],
) -> None:
    """Test coordinator _async_update_stop."""
    plan_result = JourneyPlanResult.model_validate(plan_response_data)

    with patch("custom_components.translink.coordinator.async_get_clientsession"):
        coordinator = TranslinkCoordinator(hass, stop_entry)

    coordinator.client.plan_journey = AsyncMock(return_value=plan_result)
    coordinator.client.fetch_trip_updates = AsyncMock(return_value={})
    coordinator._store.async_save = AsyncMock()

    summary = await coordinator._async_update_data()
    assert isinstance(summary, StopSummary)
    assert summary.stop_id == "ST:place_romsta"
    assert summary.stop_name == "Roma Street station"


async def test_coordinator_update_failure_raises(
    hass: HomeAssistant, journey_entry: MockConfigEntry
) -> None:
    """Test coordinator raises UpdateFailed on API error."""
    with patch("custom_components.translink.coordinator.async_get_clientsession"):
        coordinator = TranslinkCoordinator(hass, journey_entry)

    coordinator.client.plan_journey = AsyncMock(
        side_effect=TranslinkConnectionError("Network timeout")
    )
    coordinator.client.fetch_vehicle_positions = AsyncMock(return_value={})
    coordinator.client.fetch_trip_updates = AsyncMock(return_value={})

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_shutdown(
    hass: HomeAssistant, journey_entry: MockConfigEntry
) -> None:
    """Test coordinator shutdown cleanly closes client."""
    with patch("custom_components.translink.coordinator.async_get_clientsession"):
        coordinator = TranslinkCoordinator(hass, journey_entry)

    coordinator.client.close = AsyncMock()
    await coordinator.async_shutdown()
    coordinator.client.close.assert_awaited_once()
