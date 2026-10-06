"""Diagnostics support for Translink Queensland integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .client import redact_sensitive
from .const import DOMAIN
from .coordinator import TranslinkCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return redacted diagnostics for a config entry."""
    coordinator: TranslinkCoordinator | None = getattr(
        entry, "runtime_data", None
    ) or hass.data.get(DOMAIN, {}).get(entry.entry_id)

    raw_data = (
        coordinator.data.model_dump(mode="json")
        if coordinator and coordinator.data
        else None
    )

    return {
        "entry": redact_sensitive(dict(entry.data)),
        "options": redact_sensitive(dict(entry.options)),
        "data": redact_sensitive(raw_data),
    }
