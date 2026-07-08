"""The Swift Command integration."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_ENDPOINT,
    ATTR_PAYLOAD,
    DOMAIN,
    PLATFORMS,
    SERVICE_SEND_CAN_COMMAND,
)
from .coordinator import SwiftCommandCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_CAN_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENDPOINT): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
        vol.Required(ATTR_PAYLOAD): vol.All(cv.ensure_list, [vol.Coerce(int)]),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Swift Command from a config entry."""
    coordinator = SwiftCommandCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    _async_register_services(hass)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_CAN_COMMAND):
        return

    async def handle_send_can_command(call: ServiceCall) -> None:
        """Service: swift_command.send_can_command."""
        coordinators: list[SwiftCommandCoordinator] = list(
            hass.data.get(DOMAIN, {}).values()
        )
        if not coordinators:
            raise HomeAssistantError("No Swift Command config entry is loaded")
        await coordinators[0].async_send_can_command(
            call.data[ATTR_ENDPOINT], call.data[ATTR_PAYLOAD]
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_CAN_COMMAND,
        handle_send_can_command,
        schema=SERVICE_SEND_CAN_COMMAND_SCHEMA,
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SEND_CAN_COMMAND)
    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    coordinator: SwiftCommandCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.update_interval_from_options()
    await coordinator.async_request_refresh()
