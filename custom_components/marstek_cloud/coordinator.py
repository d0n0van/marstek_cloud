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
SERVER_ERROR_CODE = "500"  # Server error
API_TIMEOUT = 30
DNS_TIMEOUT = 10  # DNS resolution timeout

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


class MarstekServerError(MarstekAPIError):
    """Server error from Marstek API."""

    pass


class MarstekNetworkError(MarstekAPIError):
    """Network connectivity error."""

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
        
        # Connection pooling and DNS optimization
        self._connector = aiohttp.TCPConnector(
            limit=10,  # Total connection pool size
            limit_per_host=2,  # Max connections per host
            ttl_dns_cache=300,  # DNS cache for 5 minutes
            use_dns_cache=True,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        
    async def close(self) -> None:
        """Close the API client and cleanup resources."""
        if hasattr(self, '_connector'):
            await self._connector.close()
    
    def _get_session(self) -> aiohttp.ClientSession:
        """Get a session with optimized connection settings."""
        return aiohttp.ClientSession(
            connector=self._connector,
            timeout=aiohttp.ClientTimeout(total=API_TIMEOUT, connect=DNS_TIMEOUT),
            headers={'User-Agent': 'HomeAssistant-MarstekCloud/0.5.0'}
        )

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

            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT, connect=DNS_TIMEOUT)
            async with self._session.post(API_LOGIN, params=params, timeout=timeout) as resp:
                    if resp.status == 500:
                        raise MarstekServerError(f"Server error during login: {resp.status}")
                    elif resp.status != 200:
                        raise MarstekAuthenticationError(
                            f"Login failed with status {resp.status}"
                        )

                    data = await resp.json()
                    if "token" not in data:
                        raise MarstekAuthenticationError(f"Login failed: {data}")

                    self._token = data["token"]
                    # Set token expiration (assume 1 hour, refresh 5 minutes before)
                    self._token_expires_at = datetime.now() + timedelta(hours=1)
                    _LOGGER.info("Successfully obtained new API token (expires at %s)", 
                               self._token_expires_at.strftime("%Y-%m-%d %H:%M:%S"))

        except aiohttp.ClientConnectorError as ex:
            if "Timeout while contacting DNS servers" in str(ex):
                raise MarstekNetworkError(f"DNS resolution failed: {ex}") from ex
            else:
                raise MarstekNetworkError(f"Connection error during login: {ex}") from ex
        except aiohttp.ClientError as ex:
            raise MarstekNetworkError(f"Network error during login: {ex}") from ex
        except asyncio.TimeoutError as ex:
            raise MarstekNetworkError("Login request timed out") from ex

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
            _LOGGER.debug("Returning cached device data (age: %.1fs)", 
                         (datetime.now() - self._cache_timestamp).total_seconds())
            return self._cached_devices

        # Check if token needs refresh
        if not self._is_token_valid() or self._should_refresh_token():
            if not self._is_token_valid():
                _LOGGER.debug("Token invalid, getting new token")
            else:
                _LOGGER.debug("Token expires soon, refreshing proactively")
            await self._get_token()

        params = {"token": self._token}

        # Enhanced retry logic for various error types
        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    _LOGGER.debug("API request attempt %d/%d", attempt + 1, max_retries + 1)
                
                timeout = aiohttp.ClientTimeout(total=API_TIMEOUT, connect=DNS_TIMEOUT)
                async with self._session.get(API_DEVICES, params=params, timeout=timeout) as resp:
                        if resp.status == 500:
                            raise MarstekServerError(f"Server error: {resp.status}")
                        elif resp.status != 200:
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
                        
                        # Handle server error code 500
                        if str(data.get("code")) == SERVER_ERROR_CODE:
                            _LOGGER.warning(
                                "Server error (code 500): %s", data.get("msg", "Unknown server error")
                            )
                            raise MarstekServerError(f"Server error: {data.get('msg', 'Unknown error')}")
                        
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
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                    continue
                else:
                    _LOGGER.error("Device fetch request timed out after %d attempts", max_retries + 1)
                    raise UpdateFailed("Device fetch request timed out") from ex
            except MarstekServerError as ex:
                if attempt < max_retries:
                    _LOGGER.warning("Server error (attempt %d/%d), waiting %ds before retry...", 
                                  attempt + 1, max_retries + 1, 5 + (attempt * 2))
                    await asyncio.sleep(5 + (attempt * 2))  # Progressive delay: 5s, 7s, 9s
                    continue
                else:
                    _LOGGER.error("Server error after %d attempts: %s", max_retries + 1, ex)
                    raise UpdateFailed(f"Server error: {ex}") from ex
            except MarstekRateLimitError as ex:
                if attempt < max_retries:
                    _LOGGER.warning("Rate limit exceeded (attempt %d/%d), waiting %ds before retry...", 
                                  attempt + 1, max_retries + 1, RATE_LIMIT_RETRY_DELAY)
                    await asyncio.sleep(RATE_LIMIT_RETRY_DELAY)
                    continue
                else:
                    _LOGGER.error("Rate limit exceeded after %d attempts", max_retries + 1)
                    raise UpdateFailed("Rate limit exceeded") from ex
            except aiohttp.ClientConnectorError as ex:
                if "Timeout while contacting DNS servers" in str(ex):
                    if attempt < max_retries:
                        _LOGGER.warning("DNS resolution failed (attempt %d/%d), retrying...", 
                                      attempt + 1, max_retries + 1)
                        await asyncio.sleep(3 + (attempt * 2))  # Progressive delay: 3s, 5s, 7s
                        continue
                    else:
                        _LOGGER.error("DNS resolution failed after %d attempts", max_retries + 1)
                        raise UpdateFailed(f"DNS resolution failed: {ex}") from ex
                else:
                    raise UpdateFailed(f"Connection error during device fetch: {ex}") from ex
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
        
    def update_scan_interval(self, new_interval: int) -> None:
        """Update the scan interval for the coordinator.
        
        Args:
            new_interval: New scan interval in seconds.
        """
        # Validate the interval
        if not (10 <= new_interval <= 3600):
            _LOGGER.warning("Invalid scan interval %d, must be between 10 and 3600 seconds", 
                          new_interval)
            return
            
        self.base_scan_interval = new_interval
        self.update_interval = timedelta(seconds=new_interval)
        _LOGGER.info("Scan interval updated to %d seconds", new_interval)
        
    async def close(self) -> None:
        """Close the coordinator and cleanup resources."""
        if hasattr(self.api, 'close'):
            await self.api.close()

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
        except MarstekServerError as ex:
            _LOGGER.error("Server error during data update: %s", ex)
            raise UpdateFailed(f"Server error: {ex}") from ex
        except MarstekNetworkError as ex:
            _LOGGER.error("Network error during data update: %s", ex)
            raise UpdateFailed(f"Network error: {ex}") from ex
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
