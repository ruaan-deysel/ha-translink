"""Device tracker platform for Translink live vehicle tracking."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.device_tracker.const import SourceType
from homeassistant.components.device_tracker.entity import TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .client import JourneySummary
from .const import CONF_NAME, DOMAIN, MODE_JOURNEY, get_vehicle_icon
from .coordinator import TranslinkCoordinator

if TYPE_CHECKING:
    from . import TranslinkConfigEntry

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TranslinkConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Translink live vehicle device tracker from config entry."""
    coordinator: TranslinkCoordinator = (
        getattr(entry, "runtime_data", None) or hass.data[DOMAIN][entry.entry_id]
    )

    if coordinator.mode == MODE_JOURNEY and coordinator.track_vehicle:
        async_add_entities([TranslinkVehicleTracker(coordinator, entry)])


class TranslinkVehicleTracker(
    CoordinatorEntity[TranslinkCoordinator],
    TrackerEntity,
):
    """Realtime vehicle tracker for Translink public transit."""

    _attr_has_entity_name = True
    _attr_translation_key = "vehicle_tracker"
    _attr_source_type = SourceType.GPS
    _attr_location_accuracy = 15.0

    def __init__(
        self,
        coordinator: TranslinkCoordinator,
        entry: TranslinkConfigEntry,
    ) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_vehicle_tracker"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information."""
        name = self.entry.data.get(CONF_NAME, "Translink")
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=name,
            manufacturer="Translink Queensland",
            model="Public Transport Journey",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def icon(self) -> str:
        """Return dynamic icon based on vehicle transport type."""
        vehicle_type = (
            self.coordinator.data.next_service_vehicle
            if isinstance(self.coordinator.data, JourneySummary)
            else None
        )
        return get_vehicle_icon(vehicle_type, default="mdi:bus-marker")

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the active vehicle."""
        if isinstance(self.coordinator.data, JourneySummary):
            return self.coordinator.data.vehicle_latitude
        return None

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the active vehicle."""
        if isinstance(self.coordinator.data, JourneySummary):
            return self.coordinator.data.vehicle_longitude
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return tracker attributes."""
        if not isinstance(self.coordinator.data, JourneySummary):
            return {}

        data = self.coordinator.data
        return {
            "vehicle_id": data.vehicle_id,
            "vehicle_label": data.vehicle_label,
            "trip_id": data.trip_id,
            "route_name": data.next_service_name,
            "vehicle_type": data.next_service_vehicle,
            "route_color": data.next_service_color,
            "bearing": data.vehicle_bearing,
            "speed": data.vehicle_speed,
            "is_live_tracked": data.vehicle_tracked,
        }

    @property
    def available(self) -> bool:
        """Return true if tracker coordinates are available."""
        return (
            super().available
            and isinstance(self.coordinator.data, JourneySummary)
            and self.coordinator.data.vehicle_latitude is not None
            and self.coordinator.data.vehicle_longitude is not None
        )
