"""Platform for button entities (manual refresh)."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SwiftCommandCoordinator
from .const import DOMAIN
from .entity import SwiftCommandEntity
from .util import get_nested_value

_LOGGER = logging.getLogger(__name__)

_WARNED_NO_VEHICLE = False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Swift Command buttons."""
    coordinator: SwiftCommandCoordinator = hass.data[DOMAIN][entry.entry_id]

    vehicle = get_nested_value(coordinator.data, ["customer_data", "vehicles", 0])

    global _WARNED_NO_VEHICLE
    if not vehicle:
        if not _WARNED_NO_VEHICLE:
            _LOGGER.warning("No vehicle data found; skipping button setup until data arrives.")
            _WARNED_NO_VEHICLE = True
        return
    _WARNED_NO_VEHICLE = False

    chassis_number = vehicle.get("chassisNumber", "unknown_chassis")

    entities: list[ButtonEntity] = [
        SwiftCommandUpdateButton(coordinator, chassis_number),
    ]

    async_add_entities(entities)


class SwiftCommandUpdateButton(SwiftCommandEntity, ButtonEntity):
    """Button that triggers an immediate data refresh."""

    def __init__(self, coordinator: SwiftCommandCoordinator, chassis_number: str) -> None:
        super().__init__(coordinator, chassis_number)
        self._attr_name = "Update Now"  # simplified
        self._attr_unique_id = f"{DOMAIN}_{self._chassis_number}_update_now"
        self._attr_icon = "mdi:update"

    async def async_press(self) -> None:
        """Handle the button press."""
        # Kick off an immediate refresh from the coordinator
        await self.coordinator.async_request_refresh()
