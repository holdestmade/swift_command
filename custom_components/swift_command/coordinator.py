"""Data update coordinator for the Swift Command integration."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta

import httpx
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CAN_BUS_BASE_URL,
    CONF_CAN_BUS_TIMEOUT,
    CONF_NIGHT_END,
    CONF_NIGHT_START,
    CONF_UPDATE_INTERVAL,
    CUSTOMER_DATA_URL,
    DEFAULT_API_TIMEOUT,
    DEFAULT_CAN_BUS_TIMEOUT,
    DEFAULT_NIGHT_END,
    DEFAULT_NIGHT_START,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    LOGIN_URL,
    NIGHT_CAN_UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class SwiftCommandCoordinator(DataUpdateCoordinator[dict]):
    """Swift Command data update coordinator."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.client = get_async_client(hass)

        self.username: str = entry.data[CONF_USERNAME]
        self.password: str = entry.data[CONF_PASSWORD]

        self.customer_id: str | None = None
        self.bearer_token: str | None = None
        self.asset_id: str | None = None

        self._last_full_update_time: datetime | None = None
        self._last_can_update_time: datetime | None = None

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

    # ----- Public getters for sensors/diagnostics -----
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

    @property
    def last_full_update_time(self) -> datetime | None:
        return self._last_full_update_time

    @property
    def last_can_update_time(self) -> datetime | None:
        return self._last_can_update_time
    # ---------------------------------------------------

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
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        return timedelta(minutes=interval_minutes)

    @callback
    def update_interval_from_options(self) -> None:
        self.update_interval = self.get_update_interval()
        _LOGGER.debug("Swift Command update interval set to %s", self.update_interval)

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.bearer_token}"} if self.bearer_token else {}

    async def _login(self) -> None:
        """Log in and store the customer ID and bearer token."""
        _LOGGER.debug("Attempting to log in to Swift Command API")
        login_payload = {"email": self.username, "password": self.password}
        try:
            response = await self.client.post(
                LOGIN_URL, json=login_payload, timeout=DEFAULT_API_TIMEOUT
            )
            response.raise_for_status()
            login_data = response.json()
        except httpx.HTTPStatusError as err:
            if err.response.status_code in (401, 403):
                raise ConfigEntryAuthFailed(f"Invalid credentials: {err}") from err
            raise UpdateFailed(f"HTTP error during login: {err}") from err
        except httpx.RequestError as err:
            raise UpdateFailed(f"Network error during login: {err}") from err
        except json.JSONDecodeError as err:
            raise UpdateFailed(f"Invalid response during login: {err}") from err

        self.customer_id = login_data.get("customerID")
        token = login_data.get("token")
        self.bearer_token = token if token and str(token).lower() != "null" else None

        if not self.customer_id or not self.bearer_token:
            raise ConfigEntryAuthFailed("Login response missing customer ID or token")
        _LOGGER.debug("Successfully logged in and obtained token")

    async def _async_ensure_login(self) -> None:
        if not self.bearer_token:
            await self._login()

    def _should_throttle_can(self, now: datetime) -> bool:
        """Return True when the CAN fetch should be skipped this cycle (night mode)."""
        night_start = self.entry.options.get(CONF_NIGHT_START, DEFAULT_NIGHT_START)
        night_end = self.entry.options.get(CONF_NIGHT_END, DEFAULT_NIGHT_END)

        if night_start == night_end:
            return False  # equal start/end disables night mode

        if night_start < night_end:
            is_night = night_start <= now.hour < night_end
        else:  # window spans midnight, e.g. 20:00 -> 08:00
            is_night = now.hour >= night_start or now.hour < night_end

        if not is_night:
            return False

        return (
            self._last_can_update_time is not None
            and (now - self._last_can_update_time) < NIGHT_CAN_UPDATE_INTERVAL
        )

    async def _fetch_customer_data(self) -> dict:
        """Fetch customer data, silently re-logging in once on HTTP 401."""
        for attempt in (1, 2):
            await self._async_ensure_login()
            self._api_calls_today += 1
            url = CUSTOMER_DATA_URL.format(customer_id=self.customer_id)
            try:
                response = await self.client.get(
                    url, headers=self._auth_headers(), timeout=DEFAULT_API_TIMEOUT
                )
                response.raise_for_status()
                customer_data = response.json()
            except httpx.HTTPStatusError as err:
                if err.response.status_code == 401 and attempt == 1:
                    _LOGGER.info("401 on customer fetch; re-logging in and retrying once")
                    self.bearer_token = None
                    continue
                self._api_calls_failed_today += 1
                if err.response.status_code == 401:
                    raise ConfigEntryAuthFailed(
                        f"Authentication failed after re-login: {err}"
                    ) from err
                raise UpdateFailed(f"HTTP error during data fetch: {err}") from err
            except httpx.RequestError as err:
                self._api_calls_failed_today += 1
                raise UpdateFailed(f"Network error during data fetch: {err}") from err
            except json.JSONDecodeError as err:
                self._api_calls_failed_today += 1
                raise UpdateFailed(f"Invalid response during data fetch: {err}") from err

            vehicles = customer_data.get("vehicles")
            if isinstance(vehicles, list) and vehicles and isinstance(vehicles[0], dict):
                self.asset_id = vehicles[0].get("asset")
            return customer_data

        raise UpdateFailed("Customer data fetch failed after retry")

    async def _fetch_can_data(self, now: datetime) -> dict:
        """Fetch CAN bus data. Failures are logged but never fatal."""
        if not self.asset_id:
            return {}

        timeout_seconds = self.entry.options.get(
            CONF_CAN_BUS_TIMEOUT, DEFAULT_CAN_BUS_TIMEOUT
        )
        url = CAN_BUS_BASE_URL.format(asset_id=self.asset_id)

        for attempt in (1, 2):
            await self._async_ensure_login()
            self._api_can_calls_today += 1
            try:
                response = await self.client.get(
                    url, headers=self._auth_headers(), timeout=timeout_seconds
                )
                response.raise_for_status()
                can_bus_data = response.json()
            except httpx.HTTPStatusError as err:
                if err.response.status_code == 401 and attempt == 1:
                    _LOGGER.info("401 on CAN fetch; re-logging in and retrying once")
                    self.bearer_token = None
                    continue
                self._api_can_calls_failed_today += 1
                _LOGGER.warning(
                    "CAN fetch HTTP error (%s): %s", err.response.status_code, err
                )
                return {}
            except (asyncio.TimeoutError, httpx.RequestError, json.JSONDecodeError) as err:
                self._api_can_calls_failed_today += 1
                _LOGGER.warning("CAN fetch error (%s): %s", type(err).__name__, err)
                return {}

            if isinstance(can_bus_data, dict) and can_bus_data:
                self._last_can_update_time = now
                return can_bus_data
            return {}

        return {}

    async def _async_update_data(self) -> dict:
        """Coordinator's normal refresh cycle (may throttle CAN at night)."""
        now = dt_util.now()
        self._rollover_counters_if_needed(now)

        customer_data = await self._fetch_customer_data()

        if self._should_throttle_can(now):
            _LOGGER.debug("Night time: skipping CAN fetch, keeping last known CAN data")
            can_bus_data = (self.data or {}).get("can_bus_data", {})
        else:
            can_bus_data = await self._fetch_can_data(now)

        self._last_full_update_time = now
        return {"customer_data": customer_data, "can_bus_data": can_bus_data}

    async def async_force_refresh(self) -> None:
        """Refresh both customer and CAN data immediately, bypassing night throttling."""
        now = dt_util.now()
        self._rollover_counters_if_needed(now)

        customer_data = await self._fetch_customer_data()
        can_bus_data = await self._fetch_can_data(now)

        self._last_full_update_time = now
        self.async_set_updated_data(
            {"customer_data": customer_data, "can_bus_data": can_bus_data}
        )

    async def async_send_can_command(self, endpoint: int, payload: list) -> None:
        """Send a raw CAN command, silently re-logging in once on HTTP 401.

        Raises HomeAssistantError on failure so entity actions and service
        calls surface the problem instead of failing silently.
        """
        for attempt in (1, 2):
            await self._async_ensure_login()
            if not self.asset_id:
                raise HomeAssistantError(
                    "No asset ID available for sending CAN command"
                )
            url = f"{CAN_BUS_BASE_URL.format(asset_id=self.asset_id)}/{endpoint}"
            try:
                response = await self.client.post(
                    url,
                    json=payload,
                    headers=self._auth_headers(),
                    timeout=DEFAULT_API_TIMEOUT,
                )
                response.raise_for_status()
                _LOGGER.debug("Sent CAN command %s to %s", payload, url)
                break
            except httpx.HTTPStatusError as err:
                if err.response.status_code == 401 and attempt == 1:
                    _LOGGER.info("401 on CAN command; re-logging in and retrying once")
                    self.bearer_token = None
                    continue
                raise HomeAssistantError(f"Error sending CAN command: {err}") from err
            except httpx.RequestError as err:
                raise HomeAssistantError(f"Error sending CAN command: {err}") from err

        # Clear the CAN timestamp so the follow-up refresh fetches fresh CAN
        # state even during night hours (the user just acted on the vehicle).
        self._last_can_update_time = None
        await self.async_request_refresh()
