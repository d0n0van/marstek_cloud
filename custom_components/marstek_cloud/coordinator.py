"""Marstek Cloud API coordinator and data fetching.

Original work by @DoctaShizzle: https://github.com/DoctaShizzle/marstek_cloud
This fork adds API optimizations, caching, and adaptive intervals.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timedelta
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
RATE_LIMIT_CODE = "5"  # Rate limit exceeded
API_TIMEOUT = 30

# API optimization constants
CACHE_TTL = 30  # Cache data for 30 seconds
TOKEN_REFRESH_BUFFER = 300  # Refresh token 5 minutes before expiry
ADAPTIVE_INTERVAL_MIN = 60  # Minimum interval (1 minute)
ADAPTIVE_INTERVAL_MAX = 300  # Maximum interval (5 minutes)

# Rate limiting constants
MAX_CONCURRENT_REQUESTS = 2  # Conservative limit based on testing
RATE_LIMIT_RETRY_DELAY = 5  # Seconds to wait after rate limit hit


class MarstekAPIError(Exception):
    """Base exception for Marstek API errors."""

    pass


class MarstekAuthenticationError(MarstekAPIError):
    """Authentication failed with Marstek API."""

    pass


class MarstekPermissionError(MarstekAPIError):
    """No access permission to Marstek API."""

    pass


class MarstekRateLimitError(MarstekAPIError):
    """Rate limit exceeded for Marstek API."""

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
        self._token_expires_at: datetime | None = None
        
        # Caching for API optimization
        self._cached_devices: list[dict[str, Any]] | None = None
        self._cache_timestamp: datetime | None = None
        self._last_data_hash: str | None = None

    def _is_token_valid(self) -> bool:
        """Check if current token is still valid."""
        if not self._token or not self._token_expires_at:
            return False
        return datetime.now() < self._token_expires_at

    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid."""
        if not self._cached_devices or not self._cache_timestamp:
            return False
        return (datetime.now() - self._cache_timestamp).total_seconds() < CACHE_TTL

    def _get_data_hash(self, data: list[dict[str, Any]]) -> str:
        """Generate a hash of the data to detect changes."""
        # Create a simple hash based on key device properties
        hash_data = []
        for device in data:
            key_props = ['devid', 'soc', 'charge', 'discharge', 'load', 'profit', 'report_time']
            device_hash = {k: device.get(k) for k in key_props if k in device}
            hash_data.append(str(sorted(device_hash.items())))
        return hashlib.md5(str(hash_data).encode()).hexdigest()

    def _should_refresh_token(self) -> bool:
        """Check if token should be refreshed proactively."""
        if not self._token_expires_at:
            return True
        time_until_expiry = (self._token_expires_at - datetime.now()).total_seconds()
        return time_until_expiry < TOKEN_REFRESH_BUFFER

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
                    # Set token expiration (assume 1 hour, refresh 5 minutes before)
                    self._token_expires_at = datetime.now() + timedelta(hours=1)
                    _LOGGER.info("Successfully obtained new API token")

        except aiohttp.ClientError as ex:
            raise UpdateFailed(f"Network error during login: {ex}") from ex
        except asyncio.TimeoutError as ex:
            raise UpdateFailed("Login request timed out") from ex

    async def get_devices(self) -> list[dict[str, Any]]:
        """Fetch device list from Marstek API with caching and optimization.

        Returns:
            List of device dictionaries.

        Raises:
            MarstekPermissionError: If no access permission.
            UpdateFailed: If API request fails.
        """
        # Check if we have valid cached data
        if self._is_cache_valid():
            _LOGGER.debug("Returning cached device data")
            return self._cached_devices

        # Check if token needs refresh
        if not self._is_token_valid() or self._should_refresh_token():
            _LOGGER.debug("Token invalid or needs refresh, getting new token")
            await self._get_token()

        params = {"token": self._token}

        # Retry logic for timeout errors
        max_retries = 2
        for attempt in range(max_retries + 1):
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
                            self._token_expires_at = None
                            raise MarstekPermissionError("No access permission")
                        
                        # Handle rate limit error code 5
                        if str(data.get("code")) == RATE_LIMIT_CODE:
                            _LOGGER.warning(
                                "Rate limit exceeded (code 5). Waiting before retry."
                            )
                            raise MarstekRateLimitError("Rate limit exceeded")

                        if "data" not in data:
                            raise UpdateFailed(f"Invalid API response: {data}")

                        devices = data["data"]
                        
                        # Cache the data
                        self._cached_devices = devices
                        self._cache_timestamp = datetime.now()
                        
                        # Check if data has changed for adaptive intervals
                        current_hash = self._get_data_hash(devices)
                        if self._last_data_hash and current_hash == self._last_data_hash:
                            _LOGGER.debug("Device data unchanged, will use longer interval")
                        self._last_data_hash = current_hash

                        return devices

            except asyncio.TimeoutError as ex:
                if attempt < max_retries:
                    _LOGGER.warning("Device fetch request timed out (attempt %d/%d), retrying...", 
                                  attempt + 1, max_retries + 1)
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s
                    continue
                else:
                    _LOGGER.error("Device fetch request timed out after %d attempts", max_retries + 1)
                    raise UpdateFailed("Device fetch request timed out") from ex
            except MarstekRateLimitError as ex:
                if attempt < max_retries:
                    _LOGGER.warning("Rate limit exceeded (attempt %d/%d), waiting %ds before retry...", 
                                  attempt + 1, max_retries + 1, RATE_LIMIT_RETRY_DELAY)
                    await asyncio.sleep(RATE_LIMIT_RETRY_DELAY)
                    continue
                else:
                    _LOGGER.error("Rate limit exceeded after %d attempts", max_retries + 1)
                    raise UpdateFailed("Rate limit exceeded") from ex
            except aiohttp.ClientError as ex:
                raise UpdateFailed(f"Network error during device fetch: {ex}") from ex


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
        self.base_scan_interval = scan_interval
        self.consecutive_no_changes = 0

    async def _async_update_data(self) -> list[dict[str, Any]]:
        """Fetch latest data from Marstek API with adaptive intervals.

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
            
            # Adaptive interval logic
            self._update_adaptive_interval()
            
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

    def _update_adaptive_interval(self) -> None:
        """Update scan interval based on data changes."""
        # Check if data has changed by comparing with API's data hash
        current_hash = self.api._get_data_hash(self.api._cached_devices or [])
        
        if current_hash == self.api._last_data_hash:
            # Data unchanged, increase interval gradually
            self.consecutive_no_changes += 1
            if self.consecutive_no_changes > 3:  # After 3 consecutive no-changes
                new_interval = min(
                    self.base_scan_interval * (1.5 ** (self.consecutive_no_changes - 3)),
                    ADAPTIVE_INTERVAL_MAX
                )
                if new_interval != self.update_interval.total_seconds():
                    self.update_interval = timedelta(seconds=new_interval)
                    _LOGGER.debug("Adaptive interval: %d seconds (no changes: %d)", 
                                int(new_interval), self.consecutive_no_changes)
        else:
            # Data changed, reset to base interval
            if self.consecutive_no_changes > 0:
                self.consecutive_no_changes = 0
                self.update_interval = timedelta(seconds=self.base_scan_interval)
                _LOGGER.debug("Data changed, reset to base interval: %d seconds", 
                            self.base_scan_interval)
