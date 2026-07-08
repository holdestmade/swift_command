"""Platform for sensor integration."""
from __future__ import annotations

import logging
import re
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CAN_SECTIONS, DEFAULT_CAN_SECTIONS, DOMAIN
from .coordinator import SwiftCommandCoordinator
from .entity import SwiftCommandEntity
from .util import calculate_power_watts, get_nested_value

_LOGGER = logging.getLogger(__name__)

_WARNED_NO_VEHICLE = False  # throttle noisy logs when vehicle payload is absent

_NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")

# Firmware/identity-like CAN fields that belong in diagnostics
_DIAGNOSTIC_CAN_KEYS = {
    "cpsoftwareversionnumber",
    "psusoftwarenumber",
    "ec630softwareversionnumber",
}

# CAN fields that have dedicated/derived sensors and must not get a dynamic one
# (these would otherwise collide on unique_id with the derived power sensors).
_EXCLUDED_CAN_KEYS = {"batteryamp", "solaramps", "accurrent", "leisurebatteryvoltage"}


def _to_float(value: str | int | float | None) -> float | None:
    """Coerce value to float. Accepts numbers or strings like '2.8A' or '240 V'."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        m = _NUM_RE.search(value.replace(",", ""))
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return None
    return None


def _flatten_json(obj: Any, prefix: str = "") -> dict[str, Any]:
    """Flatten nested dicts/lists into {'a.b[0].c': value} for diagnostics."""
    flat: dict[str, Any] = {}

    def _walk(o: Any, pfx: str) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                _walk(v, f"{pfx}.{k}" if pfx else str(k))
        elif isinstance(o, list):
            for idx, v in enumerate(o):
                _walk(v, f"{pfx}[{idx}]")
        else:
            flat[pfx] = o

    _walk(obj, prefix)
    return flat


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Swift Command sensor platform."""
    coordinator: SwiftCommandCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities: list[SensorEntity] = []

    # Get the vehicle data (assuming the first vehicle in the list)
    vehicle_data = get_nested_value(coordinator.data, ["customer_data", "vehicles", 0])
    can_bus_data = coordinator.data.get("can_bus_data", {})

    global _WARNED_NO_VEHICLE
    if not vehicle_data:
        if not _WARNED_NO_VEHICLE:
            _LOGGER.warning("No vehicle data found; skipping sensor setup until data arrives.")
            _WARNED_NO_VEHICLE = True
        return
    _WARNED_NO_VEHICLE = False

    chassis_number = vehicle_data.get("chassisNumber", "unknown_chassis")

    # Coordinator counters
    entities.extend(
        [
            SwiftCommandCounterSensor(
                coordinator,
                chassis_number,
                "API Calls Today",
                lambda: coordinator.api_calls_today,
            ),
            SwiftCommandCounterSensor(
                coordinator,
                chassis_number,
                "API (CAN) Calls Today",
                lambda: coordinator.api_can_calls_today,
            ),
            SwiftCommandCounterSensor(
                coordinator,
                chassis_number,
                "API Calls Failed Today",
                lambda: coordinator.api_calls_failed_today,
            ),
            SwiftCommandCounterSensor(
                coordinator,
                chassis_number,
                "API (CAN) Calls Failed Today",
                lambda: coordinator.api_can_calls_failed_today,
            ),
        ]
    )

    # JSON overview sensors
    entities.extend(
        [
            SwiftCommandJsonOverviewSensor(coordinator, chassis_number, "Data", "customer_data"),
            SwiftCommandJsonOverviewSensor(coordinator, chassis_number, "Data (CAN)", "can_bus_data"),
        ]
    )

    # Identity/info-only sensors -> Diagnostics
    customer_data_sensors = [
        {
            "name_suffix": "Chassis Number",
            "value_path": ["customer_data", "vehicles", 0, "chassisNumber"],
            "icon": "mdi:car-chassis",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        {
            "name_suffix": "Brand Name",
            "value_path": ["customer_data", "vehicles", 0, "model", "brandName"],
            "icon": "mdi:car-info",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        {
            "name_suffix": "Model Name",
            "value_path": ["customer_data", "vehicles", 0, "model", "name"],
            "icon": "mdi:car-estate",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        {
            "name_suffix": "Model Year",
            "value_path": ["customer_data", "vehicles", 0, "model", "year"],
            "icon": "mdi:calendar",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        {
            "name_suffix": "Leisure Voltage",
            "value_path": ["customer_data", "vehicles", 0, "lastPosition", "leisureVoltage"],
            "unit_of_measurement": "V",
            "device_class": SensorDeviceClass.VOLTAGE,
            "state_class": SensorStateClass.MEASUREMENT,
        },
        {
            "name_suffix": "Alarm Triggered Leisure Voltage",
            "value_path": ["customer_data", "vehicles", 0, "lastPosition", "alarmTriggeredLeisureVoltage"],
            "unit_of_measurement": "V",
            "device_class": SensorDeviceClass.VOLTAGE,
            "state_class": SensorStateClass.MEASUREMENT,
        },
    ]

    # Derived power sensors: amps * (measured or default volts) -> watts
    can_bus_power_sensors = [
        {
            "name_suffix": "Battery Power",
            "value_path": ["can_bus_data", "levels3", "batteryAmp"],  # A
            "default_voltage": 12.0,
            "voltage_path": ["can_bus_data", "levels3", "leisureBatteryVoltage"],
            "unit_of_measurement": "W",
            "device_class": SensorDeviceClass.POWER,
            "state_class": SensorStateClass.MEASUREMENT,
        },
        {
            "name_suffix": "Solar Power",
            "value_path": ["can_bus_data", "levels3", "solarAmps"],  # A
            "default_voltage": 18.0,
            "voltage_path": ["can_bus_data", "levels3", "solarVoltage"],
            "unit_of_measurement": "W",
            "device_class": SensorDeviceClass.POWER,
            "state_class": SensorStateClass.MEASUREMENT,
        },
        {
            "name_suffix": "Mains Power",
            "value_path": ["can_bus_data", "levels3", "acCurrent"],  # A
            "default_voltage": 240.0,
            "voltage_path": ["can_bus_data", "levels3", "acVoltage"],
            "unit_of_measurement": "W",
            "device_class": SensorDeviceClass.POWER,
            "state_class": SensorStateClass.MEASUREMENT,
        },
    ]

    for sensor_info in customer_data_sensors + can_bus_power_sensors:
        entities.append(
            SwiftCommandSensor(
                coordinator,
                chassis_number,
                sensor_info["name_suffix"],
                sensor_info["value_path"],
                unit_of_measurement=sensor_info.get("unit_of_measurement"),
                device_class=sensor_info.get("device_class"),
                state_class=sensor_info.get("state_class"),
                icon=sensor_info.get("icon"),
                default_voltage=sensor_info.get("default_voltage"),
                voltage_path=sensor_info.get("voltage_path"),
                entity_category=sensor_info.get("entity_category"),
            )
        )

    # Sensors from CAN bus data (dynamic creation for remaining numeric/string values)
    def add_can_sensors(data: dict, base_value_path: list) -> None:
        if not isinstance(data, dict):
            return

        for key, value in data.items():
            if key == "id":
                continue

            current_full_path = base_value_path + [key]
            if isinstance(value, dict):
                add_can_sensors(value, current_full_path)
                continue

            if isinstance(value, bool):
                # Booleans are handled by binary_sensor.py
                continue

            k = key.lower()
            if k in _EXCLUDED_CAN_KEYS:
                continue

            human_readable_key = key.replace("_", " ").title().replace("Psu", "PSU")

            device_class = None
            state_class = None
            unit_of_measurement = None
            entity_category = None

            if isinstance(value, (int, float, str)) and k in _DIAGNOSTIC_CAN_KEYS:
                entity_category = EntityCategory.DIAGNOSTIC

            if isinstance(value, (int, float)):
                state_class = SensorStateClass.MEASUREMENT
                if "voltage" in k:
                    device_class = SensorDeviceClass.VOLTAGE
                    unit_of_measurement = "V"
                elif "current" in k:
                    device_class = SensorDeviceClass.CURRENT
                    unit_of_measurement = "A"
                elif "temp" in k:
                    device_class = SensorDeviceClass.TEMPERATURE
                    unit_of_measurement = "°C"
                elif "humiditylevel" in k:
                    device_class = SensorDeviceClass.HUMIDITY
                    unit_of_measurement = "%"

            entities.append(
                SwiftCommandSensor(
                    coordinator,
                    chassis_number,
                    human_readable_key,
                    ["can_bus_data"] + current_full_path,
                    unit_of_measurement=unit_of_measurement,
                    device_class=device_class,
                    state_class=state_class,
                    entity_category=entity_category,
                )
            )

    can_sections = config_entry.options.get(CONF_CAN_SECTIONS, DEFAULT_CAN_SECTIONS)
    for section in can_sections:
        if section_data := can_bus_data.get(section):
            add_can_sensors(section_data, [section])

    # Coordinator last successful update timestamp(s)
    entities.append(SwiftCommandTimestampSensor(coordinator, chassis_number, "Last Update"))
    entities.append(SwiftCommandTimestampSensor(coordinator, chassis_number, "Last CAN Update", can=True))

    async_add_entities(entities)


class SwiftCommandSensor(SwiftCommandEntity, SensorEntity):
    """Representation of a Swift Command Sensor."""

    def __init__(
        self,
        coordinator: SwiftCommandCoordinator,
        chassis_number: str,
        name_suffix: str,
        value_path: list,
        *,
        unit_of_measurement: str | None = None,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        icon: str | None = None,
        default_voltage: float | None = None,
        voltage_path: list | None = None,
        entity_category: EntityCategory | None = None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, chassis_number)
        self._attr_name = name_suffix
        self._value_path = value_path
        self._attr_native_unit_of_measurement = unit_of_measurement
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._attr_icon = icon
        self._attr_entity_category = entity_category
        self._default_voltage = float(default_voltage) if default_voltage is not None else None
        self._voltage_path = voltage_path

        unique_id_part = "_".join(map(str, value_path)).lower().replace("can_bus_data_", "")
        self._attr_unique_id = f"{DOMAIN}_{self._chassis_number}_{unique_id_part}_sensor"

    @property
    def native_value(self):
        raw_value = get_nested_value(self.coordinator.data, self._value_path)

        # Derived calculation: amps * volts -> watts
        if self._default_voltage is not None:
            amps = _to_float(raw_value)
            measured_volts = (
                _to_float(get_nested_value(self.coordinator.data, self._voltage_path))
                if self._voltage_path
                else None
            )
            return calculate_power_watts(
                amps, measured_volts, self._default_voltage, absolute=True
            )

        # Plain value passthrough
        return raw_value


class SwiftCommandCounterSensor(SwiftCommandEntity, SensorEntity):
    """Expose simple integer counters from the coordinator."""

    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: SwiftCommandCoordinator,
        chassis_number: str,
        name_suffix: str,
        getter: Callable[[], int],
    ) -> None:
        super().__init__(coordinator, chassis_number)
        self._getter = getter
        self._attr_name = name_suffix
        slug = name_suffix.lower().replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_{self._chassis_number}_counter_{slug}"

    @property
    def native_value(self) -> int:
        return int(self._getter())


class SwiftCommandTimestampSensor(SwiftCommandEntity, SensorEntity):
    """Expose last successful update timestamps from the coordinator."""

    _attr_icon = "mdi:update"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: SwiftCommandCoordinator,
        chassis_number: str,
        name_suffix: str,
        *,
        can: bool = False,
    ) -> None:
        super().__init__(coordinator, chassis_number)
        self._attr_name = name_suffix
        key = "last_can_update" if can else "last_full_update"
        self._attr_unique_id = f"{DOMAIN}_{self._chassis_number}_{key}"
        self._for_can = can

    @property
    def native_value(self):
        if self._for_can:
            return self.coordinator.last_can_update_time
        return self.coordinator.last_full_update_time


class SwiftCommandJsonOverviewSensor(SwiftCommandEntity, SensorEntity):
    """Diagnostic sensor: number of keys + expose full JSON payload as attributes."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:code-json"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: SwiftCommandCoordinator,
        chassis_number: str,
        name_suffix: str,
        root_key: str,
    ) -> None:
        super().__init__(coordinator, chassis_number)
        self._root_key = root_key
        self._attr_name = name_suffix
        self._attr_unique_id = f"{DOMAIN}_{self._chassis_number}_json_{root_key}"

    def _payload(self) -> dict | None:
        payload = (self.coordinator.data or {}).get(self._root_key)
        return payload if isinstance(payload, dict) else None

    @property
    def native_value(self) -> int | None:
        payload = self._payload()
        if payload is None:
            return None
        return len(_flatten_json(payload))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {}
        payload = self._payload()
        if payload is not None:
            flat = _flatten_json(payload)
            for k, v in flat.items():
                attrs[str(k)] = v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
            attrs["payload_key"] = self._root_key
            attrs["key_count"] = len(flat)
        return attrs
