"""Marstek Cloud API coordinator and data fetching."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (DataUpdateCoordinator,
                                                      UpdateFailed)

from .const import API_DEVICES, API_LOGIN

_LOGGER = logging.getLogger(__name__)

# Constants for API error handling
TOKEN_ERROR_CODES = ("-1", "401", "403")
NO_ACCESS_CODE = "8"
API_TIMEOUT = 10


class MarstekAPIError(Exception):
    """Base exception for Marstek API errors."""

    pass


class MarstekAuthenticationError(MarstekAPIError):
    """Authentication failed with Marstek API."""

    pass


class MarstekPermissionError(MarstekAPIError):
    """No access permission to Marstek API."""

    pass


class MarstekAPI:
    """Handle API communication with Marstek Cloud."""

    def __init__(
        self, session: aiohttp.ClientSession, email: str, password: str
    ) -> None:
        """Initialize the Marstek API client.

        Args:
            session: aiohttp session for HTTP requests.
            email: User email for authentication.
            password: User password for authentication.
        """
        self._session = session
        self._email = email
        self._password = password
        self._token: str | None = None

    async def _get_token(self) -> None:
        """Obtain authentication token from Marstek API.

        Raises:
            MarstekAuthenticationError: If authentication fails.
            UpdateFailed: If API request fails.
        """
        try:
            md5_pwd = hashlib.md5(self._password.encode()).hexdigest()
            params = {"pwd": md5_pwd, "mailbox": self._email}

            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            async with self._session.post(API_LOGIN, params=params, timeout=timeout) as resp:
                    if resp.status != 200:
                        raise MarstekAuthenticationError(
                            f"Login failed with status {resp.status}"
                        )

                    data = await resp.json()
                    if "token" not in data:
                        raise MarstekAuthenticationError(f"Login failed: {data}")

                    self._token = data["token"]
                    _LOGGER.info("Successfully obtained new API token")

        except aiohttp.ClientError as ex:
            raise UpdateFailed(f"Network error during login: {ex}") from ex
        except asyncio.TimeoutError as ex:
            raise UpdateFailed("Login request timed out") from ex

    async def get_devices(self) -> list[dict[str, Any]]:
        """Fetch device list from Marstek API.

        Returns:
            List of device dictionaries.

        Raises:
            MarstekPermissionError: If no access permission.
            UpdateFailed: If API request fails.
        """
        if not self._token:
            await self._get_token()

        params = {"token": self._token}

        try:
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            async with self._session.get(API_DEVICES, params=params, timeout=timeout) as resp:
                    if resp.status != 200:
                        raise UpdateFailed(
                            f"API request failed with status {resp.status}"
                        )

                    data = await resp.json()
                    _LOGGER.debug("Marstek API response: %s", data)

                    # Handle token expiration or invalid token
                    if (
                        str(data.get("code")) in TOKEN_ERROR_CODES
                        or "token" in str(data).lower()
                    ):
                        _LOGGER.warning("Token expired or invalid, refreshing...")
                        await self._get_token()
                        params["token"] = self._token

                        async with self._session.get(
                            API_DEVICES, params=params, timeout=timeout
                        ) as retry_resp:
                            if retry_resp.status != 200:
                                raise UpdateFailed(
                                    f"Retry request failed with status {retry_resp.status}"
                                )
                            data = await retry_resp.json()
                            _LOGGER.debug("Marstek API retry response: %s", data)

                    # Handle specific error code 8 (no access permission)
                    if str(data.get("code")) == NO_ACCESS_CODE:
                        _LOGGER.error(
                            "No access permission (code 8). Clearing token for retry."
                        )
                        self._token = None
                        raise MarstekPermissionError("No access permission")

                    if "data" not in data:
                        raise UpdateFailed(f"Invalid API response: {data}")

                    return data["data"]

        except aiohttp.ClientError as ex:
            raise UpdateFailed(f"Network error during device fetch: {ex}") from ex
        except asyncio.TimeoutError as ex:
            raise UpdateFailed("Device fetch request timed out") from ex


class MarstekCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    """Coordinator for Marstek Cloud data updates."""

    def __init__(
        self, hass: HomeAssistant, api: MarstekAPI, scan_interval: int
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance.
            api: Marstek API client.
            scan_interval: Update interval in seconds.
        """
        super().__init__(
            hass,
            logger=_LOGGER,
            name="Marstek Cloud",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self.last_latency: float | None = None

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch latest data from Marstek API.

        Returns:
            List of device data dictionaries.

        Raises:
            UpdateFailed: If data fetch fails.
        """
        try:
            start = time.perf_counter()
            devices = await self.api.get_devices()
            self.last_latency = round((time.perf_counter() - start) * 1000, 1)

            _LOGGER.debug(
                "Fetched %d devices in %.1f ms", len(devices), self.last_latency
            )
            return devices

        except MarstekPermissionError as ex:
            _LOGGER.warning("Permission error, will retry later: %s", ex)
            raise UpdateFailed(f"Permission error: {ex}") from ex
        except MarstekAPIError as ex:
            _LOGGER.error("API error: %s", ex)
            raise UpdateFailed(f"API error: {ex}") from ex
        except Exception as ex:
            _LOGGER.error("Unexpected error during data update: %s", ex)
            raise UpdateFailed(f"Unexpected error: {ex}") from ex
