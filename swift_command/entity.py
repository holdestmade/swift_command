"""Base entity for the Swift Command integration."""
from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SwiftCommandCoordinator
from .const import DOMAIN
from .util import get_nested_value


class SwiftCommandEntity(CoordinatorEntity):
    """Base class for all Swift Command entities."""

    def __init__(self, coordinator: SwiftCommandCoordinator, chassis_number: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._chassis_number = chassis_number
        self.coordinator: SwiftCommandCoordinator

    @property
    def device_info(self):
        """Return device information."""
        model_name = get_nested_value(
            self.coordinator.data, ["customer_data", "vehicles", 0, "model", "brandName"]
        )

        return {
            "identifiers": {(DOMAIN, self._chassis_number)},
            "name": f"Swift Command ({self._chassis_number})",
            "manufacturer": "Sargent Electrical Services Ltd.",
            "model": model_name or "Unknown",
        }
