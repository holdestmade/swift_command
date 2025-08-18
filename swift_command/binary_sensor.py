"""Platform for binary sensor integration."""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import SwiftCommandCoordinator
from .const import DOMAIN
from .entity import SwiftCommandEntity
from .util import get_nested_value

_LOGGER = logging.getLogger(__name__)

_WARNED_NO_VEHICLE = False


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Swift Command binary sensor platform."""
    coordinator: SwiftCommandCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[BinarySensorEntity] = []

    vehicle_data = get_nested_value(coordinator.data, ["customer_data", "vehicles", 0])
    can_bus_data = coordinator.data.get("can_bus_data", {})

    global _WARNED_NO_VEHICLE
    if not vehicle_data:
        if not _WARNED_NO_VEHICLE:
            _LOGGER.warning("No vehicle data found; skipping binary sensors until data arrives.")
            _WARNED_NO_VEHICLE = True
        return
    _WARNED_NO_VEHICLE = False

    chassis_number = vehicle_data.get("chassisNumber", "unknown_chassis")

    # Overall API status (diagnostic)
    entities.append(SwiftCommandTokenSensor(coordinator, chassis_number))
    entities.append(SwiftCommandCanStatusSensor(coordinator, chassis_number))

    # Recursively find boolean values and create binary sensors
    def add_can_binary_sensors(data: dict, base_value_path: list):
        if not isinstance(data, dict):
            return

        for key, value in data.items():
            if key == "id":
                continue

            current_full_path = base_value_path + [key]
            if isinstance(value, dict):
                add_can_binary_sensors(value, current_full_path)
            elif isinstance(value, bool):
                human_readable_key = key.replace("_", " ").title().replace("Psu", "PSU")

                device_class = None
                icon = None

                lower_key = key.lower()
                if any(x in lower_key for x in ["poweron", "mains", "acpresent"]):
                    device_class = BinarySensorDeviceClass.POWER
                elif any(x in lower_key for x in ["warning", "fault", "error"]):
                    device_class = BinarySensorDeviceClass.PROBLEM
                elif any(x in lower_key for x in ["run", "pump"]):
                    device_class = BinarySensorDeviceClass.RUNNING

                entities.append(
                    SwiftCommandBinarySensor(
                        coordinator,
                        chassis_number,
                        human_readable_key,
                        ["can_bus_data"] + current_full_path,
                        device_class,
                        icon,
                    )
                )

    can_sections = config_entry.options.get(
        "can_sections",
        [
            "psuStatus1",
            "psuStatus2",
            "psuWarnings1",
            "psuWarnings2",
            "levels3",
            "currentOptionsBank3",
            "currentOptionsBank1",
            "currentOptionsBank2",
        ],
    )
    for section in can_sections:
        if section_data := can_bus_data.get(section):
            add_can_binary_sensors(section_data, [section])

    async_add_entities(entities)


class SwiftCommandTokenSensor(SwiftCommandEntity, BinarySensorEntity):
    """Represents the overall Swift Command API token status."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: SwiftCommandCoordinator, chassis_number: str) -> None:
        super().__init__(coordinator, chassis_number)
        self._attr_unique_id = f"{DOMAIN}_{self._chassis_number}_api_token_status"
        self._attr_name = "API Status"  # simplified

    @property
    def is_on(self) -> bool:
        """True if we currently hold a bearer token."""
        return self.coordinator.bearer_token is not None


class SwiftCommandCanStatusSensor(SwiftCommandEntity, BinarySensorEntity):
    """Represents whether CAN data was available on the latest refresh."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: SwiftCommandCoordinator, chassis_number: str) -> None:
        super().__init__(coordinator, chassis_number)
        self._attr_unique_id = f"{DOMAIN}_{self._chassis_number}_api_can_status"
        self._attr_name = "API Status (CAN)"  # simplified

    @property
    def is_on(self) -> bool:
        """True when the latest coordinator data includes CAN content."""
        data = getattr(self.coordinator, "data", {}) or {}
        can_data = data.get("can_bus_data") or {}
        if not isinstance(can_data, dict) or not can_data:
            return False
        return "levels3" in can_data and isinstance(can_data["levels3"], dict)


class SwiftCommandBinarySensor(SwiftCommandEntity, BinarySensorEntity):
    """Representation of a dynamically discovered Swift Command Binary Sensor."""

    def __init__(
        self,
        coordinator: SwiftCommandCoordinator,
        chassis_number: str,
        name_suffix: str,
        value_path: list,
        device_class: BinarySensorDeviceClass | None = None,
        icon: str | None = None,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, chassis_number)
        self._name_suffix = name_suffix
        self._value_path = value_path
        self._attr_device_class = device_class
        self._attr_icon = icon
        self._attr_unique_id = (
            f"{DOMAIN}_binary_{self._chassis_number}_{'_'.join(map(str, self._value_path)).lower()}"
        )

    @property
    def name(self) -> str:
        """Return the name of the binary sensor."""
        return self._name_suffix  # simplified

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        return get_nested_value(self.coordinator.data, self._value_path)
