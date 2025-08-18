"""Platform for light integration."""
from __future__ import annotations

import logging

from homeassistant.components.light import ColorMode, LightEntity
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
    """Set up Swift Command light platform."""
    coordinator: SwiftCommandCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    vehicle_data = get_nested_value(coordinator.data, ["customer_data", "vehicles", 0])

    global _WARNED_NO_VEHICLE
    if not vehicle_data:
        if not _WARNED_NO_VEHICLE:
            _LOGGER.warning("No vehicle data found; skipping light setup until data arrives.")
            _WARNED_NO_VEHICLE = True
        return
    _WARNED_NO_VEHICLE = False

    chassis_number = vehicle_data.get("chassisNumber", "unknown_chassis")

    entities = []

    lights_to_add = [
        {
            "name_suffix": "All Lights",
            "state_path": ["can_bus_data", "psuStatus1", "lightsOn"],
            "toggle_payload": [5, 19, 100, 100, 4, 0, 0, 0],
            "icon": "mdi:lightbulb",
        },
        {
            "name_suffix": "Awning Light",
            "state_path": ["can_bus_data", "psuStatus1", "awningLightsOn"],
            "toggle_payload": [6, 19, 100, 100, 4, 0, 0, 0],
            "icon": "mdi:outdoor-lamp",
        },
        {
            "name_suffix": "Dimmer 1 Light",
            "state_path": ["can_bus_data", "psuStatus2", "dim1on"],
            "toggle_payload": [9, 19, 100, 100, 4, 0, 0, 0],
            "icon": "mdi:lightbulb-on-outline",
        },
        {
            "name_suffix": "Dimmer 2 Light",
            "state_path": ["can_bus_data", "psuStatus2", "dim2on"],
            "toggle_payload": [10, 19, 100, 100, 4, 0, 0, 0],
            "icon": "mdi:lightbulb-on-outline",
        },
    ]

    for light_info in lights_to_add:
        entities.append(
            SwiftCommandLight(
                coordinator,
                chassis_number,
                light_info["name_suffix"],
                light_info["state_path"],
                light_info["toggle_payload"],
                light_info["icon"],
            )
        )

    async_add_entities(entities)


class SwiftCommandLight(SwiftCommandEntity, LightEntity):
    """Representation of a Swift Command Light."""

    def __init__(
        self,
        coordinator: SwiftCommandCoordinator,
        chassis_number: str,
        name_suffix: str,
        state_path: list,
        toggle_payload: list,
        icon: str,
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator, chassis_number)
        self._name_suffix = name_suffix
        self._state_path = state_path
        self._toggle_payload = toggle_payload
        self._attr_icon = icon

        self._attr_supported_color_modes = {ColorMode.ONOFF}
        self._override_state = None
        self._attr_color_mode = ColorMode.ONOFF

        unique_id_part = "_".join(map(str, state_path)).lower().replace("can_bus_data_", "")
        self._attr_unique_id = f"{DOMAIN}_{self._chassis_number}_{unique_id_part}_light"
        self._attr_name = self._name_suffix  # simplified

    @property
    def is_on(self) -> bool | None:
        """Return true if the light is on."""
        if self._override_state is not None:
            return self._override_state
        return get_nested_value(self.coordinator.data, self._state_path)

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on."""
        await self._send_toggle_command()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        await self._send_toggle_command()

    async def _send_toggle_command(self) -> None:
        """Send the toggle command to the API."""
        # Optimistic state flip
        current = self.is_on
        self._override_state = (not current) if current is not None else True
        self.async_write_ha_state()

        # Send via centralized coordinator method (endpoint 11 for lights)
        await self.coordinator.async_send_can_command(11, self._toggle_payload)
        # Clear optimistic override after refresh
        self._override_state = None
