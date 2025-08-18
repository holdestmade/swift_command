"""Config flow for Swift Command integration."""
import logging

import httpx
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from homeassistant.helpers.httpx_client import get_async_client

from .const import (
    DEFAULT_CAN_BUS_TIMEOUT,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_START,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_CAN_SECTIONS,
    DOMAIN,
    LOGIN_URL,
)

_LOGGER = logging.getLogger(__name__)


async def validate_input(hass: HomeAssistant, data: dict) -> dict:
    """Validate the user input allows us to connect to Swift Command."""
    client = get_async_client(hass)
    try:
        login_payload = {"email": data[CONF_USERNAME], "password": data[CONF_PASSWORD]}
        response = await client.post(LOGIN_URL, json=login_payload, timeout=10)
        response.raise_for_status()
        login_data = response.json()
        if not login_data.get("customerID") or not login_data.get("token"):
            raise InvalidAuth("Login successful but customerID or token missing.")
        return {"title": f"Swift Command ({data[CONF_USERNAME]})"}
    except httpx.HTTPStatusError as err:
        if err.response.status_code == 401:
            raise InvalidAuth from err
        raise CannotConnect from err
    except httpx.RequestError as err:
        raise CannotConnect from err


class SwiftCommandConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Swift Command."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return SwiftCommandOptionsFlow()

    async def async_step_reauth(self, user_input=None):
        """Start reauthentication flow."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(self.context.get("entry_id")) if self.context else None
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                # Update the existing entry with new creds
                if self._reauth_entry:
                    data = {**self._reauth_entry.data, CONF_USERNAME: user_input[CONF_USERNAME], CONF_PASSWORD: user_input[CONF_PASSWORD]}
                    self.hass.config_entries.async_update_entry(self._reauth_entry, data=data)
                    await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id="reauth_confirm", data_schema=schema, errors=errors)


class SwiftCommandOptionsFlow(config_entries.OptionsFlow):
    """Handle an options flow for Swift Command."""

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    "update_interval",
                    default=options.get("update_interval", DEFAULT_UPDATE_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=1440,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="minutes",
                    )
                ),
                vol.Required(
                    "can_bus_timeout",
                    default=options.get("can_bus_timeout", DEFAULT_CAN_BUS_TIMEOUT),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=5,
                        max=60,
                        mode=selector.NumberSelectorMode.BOX,
                        unit_of_measurement="seconds",
                    )
                ),
                vol.Required(
                    "night_start_hour",
                    default=options.get("night_start_hour", DEFAULT_NIGHT_START),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=23, mode=selector.NumberSelectorMode.SLIDER
                    )
                ),
                vol.Required(
                    "night_end_hour",
                    default=options.get("night_end_hour", DEFAULT_NIGHT_END),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0, max=23, mode=selector.NumberSelectorMode.SLIDER
                    )
                ),
                vol.Optional(
                    "can_sections",
                    default=self.config_entry.options.get("can_sections", DEFAULT_CAN_SECTIONS),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=DEFAULT_CAN_SECTIONS, multiple=True, mode=selector.SelectSelectorMode.LIST)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)


class InvalidAuth(HomeAssistantError):
    """Error to indicate invalid credentials."""


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
