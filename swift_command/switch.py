"""Platform for switch integration."""
from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from . import SwiftCommandCoordinator
from .entity import SwiftCommandEntity
from .util import get_nested_value

_LOGGER = logging.getLogger(__name__)

_WARNED_NO_VEHICLE = False


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Swift Command switch platform."""
    coordinator: SwiftCommandCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    vehicle_data = get_nested_value(coordinator.data, ["customer_data", "vehicles", 0])

    global _WARNED_NO_VEHICLE
    if not vehicle_data:
        if not _WARNED_NO_VEHICLE:
            _LOGGER.warning("No vehicle data found; skipping switch setup until data arrives.")
            _WARNED_NO_VEHICLE = True
        return
    _WARNED_NO_VEHICLE = False

    chassis_number = vehicle_data.get("chassisNumber", "unknown_chassis")
    async_add_entities([SwiftCommandPowerSwitch(coordinator, chassis_number)])


class SwiftCommandPowerSwitch(SwiftCommandEntity, SwitchEntity):
    """Representation of the Swift Command Power Switch."""

    def __init__(
        self,
        coordinator: SwiftCommandCoordinator,
        chassis_number: str,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, chassis_number)
        self._attr_unique_id = f"{DOMAIN}_{self._chassis_number}_power_switch"
        self._attr_name = "Power"  # simplified
        self._attr_icon = "mdi:power"
        self._toggle_payload = [4, 19, 100, 100, 4, 0, 0, 0]

    @property
    def is_on(self) -> bool | None:
        """Return true if the switch is on."""
        return get_nested_value(self.coordinator.data, ["can_bus_data", "psuStatus1", "powerOn"])

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        await self._send_toggle_command()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        await self._send_toggle_command()

    async def _send_toggle_command(self) -> None:
        """Send the toggle command to the API via the coordinator service."""
        await self.coordinator.async_send_can_command(11, self._toggle_payload)
