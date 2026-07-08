"""Base entity for the Swift Command integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SwiftCommandCoordinator
from .util import get_nested_value


class SwiftCommandEntity(CoordinatorEntity[SwiftCommandCoordinator]):
    """Base class for all Swift Command entities."""

    def __init__(self, coordinator: SwiftCommandCoordinator, chassis_number: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._chassis_number = chassis_number

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        model_path = ["customer_data", "vehicles", 0, "model"]
        brand = get_nested_value(self.coordinator.data, model_path + ["brandName"])
        model = get_nested_value(self.coordinator.data, model_path + ["name"])

        return DeviceInfo(
            identifiers={(DOMAIN, self._chassis_number)},
            name=f"Swift Command ({self._chassis_number})",
            manufacturer="Sargent Electrical Services Ltd.",
            model=" ".join(str(p) for p in (brand, model) if p) or "Unknown",
        )
