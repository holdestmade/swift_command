"""The Swift Command integration."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, date

import httpx
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CAN_BUS_BASE_URL,
    CUSTOMER_DATA_URL,
    DEFAULT_CAN_BUS_TIMEOUT,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_START,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGIN_URL,
    PLATFORMS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Swift Command from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = SwiftCommandCoordinator(hass, entry)

    async def handle_send_can_command(call):
        """Service: swift_command.send_can_command"""
        endpoint = call.data.get("endpoint")
        payload = call.data.get("payload")
        await coordinator.async_send_can_command(endpoint, payload)

    hass.services.async_register(DOMAIN, "send_can_command", handle_send_can_command)

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    coordinator: SwiftCommandCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.update_interval_from_options()
    await coordinator.async_request_refresh()


class SwiftCommandCoordinator(DataUpdateCoordinator):
    """Swift Command data update coordinator."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry
        self.client = get_async_client(hass)

        self.username = entry.data["username"]
        self.password = entry.data["password"]

        self.customer_id: str | None = None
        self.bearer_token: str | None = None
        self.asset_id: str | None = None

        self._last_full_update_time: datetime | None = None
        self._last_can_update_time: datetime | None = None  # NEW: timestamp of last successful CAN payload
        self._reauth_initiated_at: datetime | None = None  # throttle reauth popups

        # -------- Daily counters (reset at local midnight) --------
        self._counter_date: date | None = None
        self._api_calls_today: int = 0
        self._api_can_calls_today: int = 0
        self._api_calls_failed_today: int = 0
        self._api_can_calls_failed_today: int = 0
        # ----------------------------------------------------------

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=self.get_update_interval(),
            config_entry=entry,
        )

    # ----- Public getters for sensors -----
    @property
    def api_calls_today(self) -> int:
        return self._api_calls_today

    @property
    def api_can_calls_today(self) -> int:
        return self._api_can_calls_today

    @property
    def api_calls_failed_today(self) -> int:
        return self._api_calls_failed_today

    @property
    def api_can_calls_failed_today(self) -> int:
        return self._api_can_calls_failed_today
    # -------------------------------------

    def _rollover_counters_if_needed(self, now: datetime) -> None:
        """Reset counters when the local date rolls over."""
        today = now.date()
        if self._counter_date != today:
            self._counter_date = today
            self._api_calls_today = 0
            self._api_can_calls_today = 0
            self._api_calls_failed_today = 0
            self._api_can_calls_failed_today = 0
            _LOGGER.debug("Swift Command counters reset for new day: %s", today)

    def get_update_interval(self) -> timedelta:
        """Get the update interval from options."""
        interval_minutes = self.entry.options.get(
            "update_interval", DEFAULT_UPDATE_INTERVAL
        )
        return timedelta(minutes=interval_minutes)

    @callback
    def update_interval_from_options(self) -> None:
        self.update_interval = self.get_update_interval()
        _LOGGER.debug("Swift Command update interval set to %s", self.update_interval)

    async def async_send_can_command(self, endpoint: int, payload: list):
        if not self.bearer_token or not self.asset_id:
            _LOGGER.error("Auth token or asset ID not available for sending CAN command.")
            return
        url = f"{CAN_BUS_BASE_URL.format(asset_id=self.asset_id)}/{endpoint}"
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        try:
            resp = await self.client.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            _LOGGER.info("Sent CAN command to %s", url)
        except (httpx.RequestError, httpx.HTTPStatusError) as err:
            _LOGGER.error("Error sending CAN command: %s", err)
        await self.async_request_refresh()

    async def _login(self) -> None:
        _LOGGER.debug("Attempting to log in to Swift Command API.")
        login_payload = {"email": self.username, "password": self.password}
        try:
            response = await self.client.post(LOGIN_URL, json=login_payload, timeout=10)
            response.raise_for_status()
            login_data = response.json()

            self.customer_id = login_data.get("customerID")
            token = login_data.get("token")
            if not token or str(token).lower() == "null":
                token = None
            self.bearer_token = token

            if not self.customer_id or not self.bearer_token:
                raise UpdateFailed("Failed to get customer ID or token from login.")
            _LOGGER.debug("Successfully logged in and obtained token.")
        except httpx.RequestError as err:
            raise UpdateFailed(f"Network error during login: {err}") from err
        except httpx.HTTPStatusError as err:
            raise UpdateFailed(f"HTTP error during login: {err}") from err

    def _should_prompt_reauth(self) -> bool:
        if self._reauth_initiated_at is None:
            return True
        return (dt_util.utcnow() - self._reauth_initiated_at) > timedelta(hours=6)

    async def _maybe_start_reauth(self) -> None:
        if not self._should_prompt_reauth():
            _LOGGER.debug("Reauth already initiated recently; suppressing popup.")
            return
        self._reauth_initiated_at = dt_util.utcnow()
        _LOGGER.info("Starting reauth flow for %s", DOMAIN)
        try:
            await self.hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "reauth", "entry_id": self.entry.entry_id},
                data=self.entry.data,
            )
        except Exception:
            _LOGGER.debug("Could not start reauth flow (already active?).")

    async def _async_update_data(self):
        now = dt_util.now()
        self._rollover_counters_if_needed(now)

        night_start = self.entry.options.get("night_start_hour", DEFAULT_NIGHT_START)
        night_end = self.entry.options.get("night_end_hour", DEFAULT_NIGHT_END)

        is_night_time = (now.hour >= night_start) or (now.hour < night_end)
        throttle_can = False
        if is_night_time and self._last_full_update_time and (now - self._last_full_update_time) < timedelta(hours=4):
            _LOGGER.debug("Night time: throttling CAN bus fetch; customer data will still refresh.")
            throttle_can = True

        if not self.bearer_token:
            await self._login()

        def _headers() -> dict[str, str]:
            return {"Authorization": f"Bearer {self.bearer_token}"} if self.bearer_token else {}

        for attempt in (1, 2):
            try:
                # ---- CUSTOMER DATA ----
                self._api_calls_today += 1
                customer_data_url = CUSTOMER_DATA_URL.format(customer_id=self.customer_id)
                customer_response = await self.client.get(
                    customer_data_url, headers=_headers(), timeout=10
                )
                customer_response.raise_for_status()
                customer_data = customer_response.json()

                self.asset_id = customer_data.get("vehicles", [{}])[0].get("asset")

                # ---- CAN DATA (optional per cycle) ----
                can_bus_data: dict = {}
                if self.asset_id and not throttle_can:
                    try:
                        self._api_can_calls_today += 1
                        timeout_seconds = self.entry.options.get(
                            "can_bus_timeout", DEFAULT_CAN_BUS_TIMEOUT
                        )
                        can_bus_url = CAN_BUS_BASE_URL.format(asset_id=self.asset_id)
                        can_response = await self.client.get(
                            can_bus_url, headers=_headers(), timeout=timeout_seconds
                        )
                        can_response.raise_for_status()
                        can_bus_data = can_response.json()
                        # NEW: mark last successful CAN payload time (only when payload present)
                        if isinstance(can_bus_data, dict) and can_bus_data:
                            self._last_can_update_time = now
                    except httpx.HTTPStatusError as cerr:
                        self._api_can_calls_failed_today += 1
                        _LOGGER.warning("CAN fetch HTTP error (%s): %s", cerr.response.status_code, cerr)
                    except (asyncio.TimeoutError, httpx.RequestError, json.JSONDecodeError) as err:
                        self._api_can_calls_failed_today += 1
                        _LOGGER.warning("CAN fetch error (%s): %s", type(err).__name__, err)

                # Update last full update timestamp after successful customer data
                self._last_full_update_time = now

                return {"customer_data": customer_data, "can_bus_data": can_bus_data}

            except httpx.HTTPStatusError as err:
                if err.response.status_code == 401 and attempt == 1:
                    _LOGGER.info("401 Unauthorized. Attempting silent re-login and retry once.")
                    self.bearer_token = None
                    try:
                        await self._login()
                        continue
                    except UpdateFailed as login_err:
                        _LOGGER.warning("Silent re-login failed: %s", login_err)
                        break
                else:
                    self._api_calls_failed_today += 1
                    raise UpdateFailed(f"HTTP error during data fetch: {err}") from err
            except httpx.RequestError as err:
                self._api_calls_failed_today += 1
                raise UpdateFailed(f"Network error during data fetch: {err}") from err

        # If we reach here, both attempts failed → prompt reauth
        await self._maybe_start_reauth()
        raise UpdateFailed("Authentication failed after retry.")
