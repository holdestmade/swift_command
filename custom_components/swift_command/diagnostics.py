"""Diagnostics support for the Swift Command integration."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN

REDACT_KEYS = {
    "customerID",
    "token",
    "asset",
    "asset_id",
    "bearer_token",
    "email",
    "username",
    "password",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data = getattr(coordinator, "data", {}) or {}

    info = {
        "update_interval_minutes": coordinator.get_update_interval().total_seconds() / 60,
        "api": {
            "calls_today": coordinator.api_calls_today,
            "calls_failed_today": coordinator.api_calls_failed_today,
            "can_calls_today": coordinator.api_can_calls_today,
            "can_calls_failed_today": coordinator.api_can_calls_failed_today,
            "last_full_update": getattr(coordinator, "_last_full_update_time", None),
            "last_can_update": getattr(coordinator, "_last_can_update_time", None),
        },
        "raw_payload": data,
    }

    return async_redact_data(info, REDACT_KEYS)
