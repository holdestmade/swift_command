"""Platform for device tracker integration."""
from __future__ import annotations

import logging

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
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
    """Set up the Swift Command device tracker platform."""
    coordinator: SwiftCommandCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = []

    vehicle_data = get_nested_value(coordinator.data, ["customer_data", "vehicles", 0])

    global _WARNED_NO_VEHICLE
    if not vehicle_data:
        if not _WARNED_NO_VEHICLE:
            _LOGGER.warning("No vehicle data found; skipping device tracker setup until data arrives.")
            _WARNED_NO_VEHICLE = True
        return
    _WARNED_NO_VEHICLE = False

    chassis_number = vehicle_data.get("chassisNumber", "unknown_chassis")
    entities.append(SwiftCommandDeviceTracker(coordinator, chassis_number))

    async_add_entities(entities)


class SwiftCommandDeviceTracker(SwiftCommandEntity, TrackerEntity):
    """Representation of the Swift Command device tracker (vehicle location)."""

    def __init__(self, coordinator: SwiftCommandCoordinator, chassis_number: str) -> None:
        super().__init__(coordinator, chassis_number)
        self._attr_unique_id = f"{DOMAIN}_{self._chassis_number}_device_tracker"
        self._attr_name = "Vehicle Location"  # simplified

    @property
    def latitude(self) -> float | None:
        return get_nested_value(
            self.coordinator.data, ["customer_data", "vehicles", 0, "lastPosition", "latitude"]
        )

    @property
    def longitude(self) -> float | None:
        return get_nested_value(
            self.coordinator.data, ["customer_data", "vehicles", 0, "lastPosition", "longitude"]
        )

    @property
    def source_type(self) -> SourceType:
        """Return the source type of the device."""
        return SourceType.GPS

    @property
    def extra_state_attributes(self):
        """Return device specific attributes."""
        attrs = {}
        if gps_accuracy := get_nested_value(
            self.coordinator.data, ["customer_data", "vehicles", 0, "lastPosition", "timeToFix"]
        ):
            attrs["time_to_fix"] = gps_accuracy
        return attrs
