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

# Security: Sensitive fields that should never be logged
_SENSITIVE_FIELDS = {"password", "token", "pwd"}


def _redact_sensitive_data(data: dict[str, Any] | Any, depth: int = 0) -> dict[str, Any] | Any:
    """Redact sensitive information from data structures for safe logging.
    
    Args:
        data: Data structure that may contain sensitive fields.
        depth: Current recursion depth (max 3 levels to prevent infinite loops).
    
    Returns:
        Data structure with sensitive fields redacted.
    """
    if depth > 3 or not isinstance(data, dict):
        return data
    
    redacted = {}
    for key, value in data.items():
        if any(sensitive in key.lower() for sensitive in _SENSITIVE_FIELDS):
            redacted[key] = "***REDACTED***"
        elif isinstance(value, dict):
            redacted[key] = _redact_sensitive_data(value, depth + 1)
        elif isinstance(value, list):
            redacted[key] = [
                _redact_sensitive_data(item, depth + 1) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            redacted[key] = value
    return redacted

# Constants for API error handling
TOKEN_ERROR_CODES = ("-1", "401", "403")
NO_ACCESS_CODE = "8"
RATE_LIMIT_CODE = "5"  # Rate limit exceeded
SERVER_ERROR_CODE = "500"  # Server error
API_TIMEOUT = 30
DNS_TIMEOUT = 10  # DNS resolution timeout

# API optimization constants
DEFAULT_CACHE_TTL = 60  # Default cache duration (should match DEFAULT_SCAN_INTERVAL)
TOKEN_REFRESH_BUFFER = 300  # Refresh token 5 minutes before expiry
ADAPTIVE_INTERVAL_MIN = 60  # Minimum interval (1 minute)
ADAPTIVE_INTERVAL_MAX = 300  # Maximum interval (5 minutes)

# Rate limiting constants
MAX_CONCURRENT_REQUESTS = 2  # Conservative limit based on testing
RATE_LIMIT_RETRY_DELAY = 5  # Seconds to wait after rate limit hit

# Server error handling constants
SERVER_ERROR_RETRY_DELAY = 10  # Seconds to wait after server error
MAX_SERVER_ERROR_RETRIES = 5  # Maximum retries for server errors
SERVER_ERROR_BACKOFF_MULTIPLIER = 2  # Exponential backoff multiplier


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
        self, session: aiohttp.ClientSession, email: str, password: str, cache_ttl: int = DEFAULT_CACHE_TTL
    ) -> None:
        """Initialize the Marstek API client.

        Args:
            session: aiohttp session for HTTP requests.
            email: User email for authentication.
            password: User password for authentication (stored securely in memory,
                     never logged, required for token refresh as API uses client-side MD5).
            cache_ttl: Cache duration in seconds (default: 60).
        
        Security Note:
            The password is stored in memory because the Marstek API requires
            client-side MD5 hashing for authentication. It is never logged or exposed.
        """
        self._session = session
        self._email = email
        # Security: Password stored in memory only, never logged
        self._password = password
        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._cache_ttl = cache_ttl
        
        # Caching for API optimization
        self._cached_devices: list[dict[str, Any]] | None = None
        self._cache_timestamp: datetime | None = None
        self._last_data_hash: str | None = None
        
        # Circuit breaker for server errors
        self._server_error_count = 0
        self._last_server_error_time: datetime | None = None
        self._circuit_breaker_threshold = 3  # Open circuit after 3 consecutive errors
        self._circuit_breaker_timeout = 300  # 5 minutes before trying again
        
        # Connection pooling and DNS optimization
        # Delay connector creation until it's actually needed (in an async context)
        self._connector: aiohttp.TCPConnector | None = None
        
    def _get_connector(self) -> aiohttp.TCPConnector:
        """Get or create the TCP connector with optimized settings."""
        if self._connector is None:
            # Connection pooling and DNS optimization
            # Only create resolver if there's a running event loop
            resolver = None
            try:
                loop = asyncio.get_running_loop()
                resolver = aiohttp.AsyncResolver(nameservers=['8.8.8.8', '1.1.1.1'])  # Reliable DNS
            except RuntimeError:
                # No event loop running (fallback to default resolver)
                pass
            
            self._connector = aiohttp.TCPConnector(
                limit=10,  # Total connection pool size
                limit_per_host=2,  # Max connections per host
                ttl_dns_cache=300,  # DNS cache for 5 minutes
                use_dns_cache=True,
                keepalive_timeout=30,
                enable_cleanup_closed=True,
                # Additional optimizations for better reliability
                force_close=False,  # Keep connections alive
                resolver=resolver  # Will be None if no event loop
            )
        return self._connector
    
    async def close(self) -> None:
        """Close the API client and cleanup resources."""
        if self._connector is not None:
            await self._connector.close()
            self._connector = None
    
    def _get_session(self) -> aiohttp.ClientSession:
        """Get a session with optimized connection settings."""
        return aiohttp.ClientSession(
            connector=self._get_connector(),
            timeout=aiohttp.ClientTimeout(
                total=API_TIMEOUT, 
                connect=DNS_TIMEOUT,
                sock_read=15,  # Socket read timeout
                sock_connect=DNS_TIMEOUT  # Socket connect timeout
            ),
            headers={
                'User-Agent': 'HomeAssistant-MarstekCloud/0.5.0',
                'Accept': 'application/json',
                'Connection': 'keep-alive'
            }
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
        return (datetime.now() - self._cache_timestamp).total_seconds() < self._cache_ttl

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

    def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker is open due to repeated server errors."""
        if self._server_error_count < self._circuit_breaker_threshold:
            return False
        
        if self._last_server_error_time is None:
            return False
            
        time_since_error = (datetime.now() - self._last_server_error_time).total_seconds()
        return time_since_error < self._circuit_breaker_timeout

    def _record_server_error(self) -> None:
        """Record a server error for circuit breaker logic."""
        self._server_error_count += 1
        self._last_server_error_time = datetime.now()
        _LOGGER.warning("Server error count: %d/%d", self._server_error_count, self._circuit_breaker_threshold)

    def _reset_circuit_breaker(self) -> None:
        """Reset circuit breaker after successful request."""
        if self._server_error_count > 0:
            _LOGGER.info("Resetting circuit breaker after successful request")
            self._server_error_count = 0
            self._last_server_error_time = None

    async def _get_token(self) -> None:
        """Obtain authentication token from Marstek API.

        Raises:
            MarstekAuthenticationError: If authentication fails.
            UpdateFailed: If API request fails.
        """
        try:
            # Security: MD5 hash password before sending (required by API)
            # The plaintext password is only used here and never logged
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
                    
                    # Check for rate limit error (code '5') in login response
                    if str(data.get("code")) == RATE_LIMIT_CODE:
                        _LOGGER.warning("Rate limit exceeded during login (code 5)")
                        raise MarstekRateLimitError("Rate limit exceeded during login")
                    
                    if "token" not in data:
                        # Security: Redact any sensitive data before logging
                        safe_data = _redact_sensitive_data(data)
                        raise MarstekAuthenticationError(f"Login failed: {safe_data}")

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
        # Check circuit breaker
        if self._is_circuit_breaker_open():
            if self._cached_devices:
                _LOGGER.warning("Circuit breaker open, returning cached data")
                return self._cached_devices
            else:
                raise MarstekServerError("Circuit breaker open - no cached data available")
        
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
                        elif resp.status == 502:
                            # 502 Bad Gateway is a transient error, retry it
                            raise MarstekServerError(f"Bad Gateway: {resp.status}")
                        elif resp.status != 200:
                            raise UpdateFailed(
                                f"API request failed with status {resp.status}"
                            )

                        data = await resp.json()
                        # Security: Redact sensitive data before logging
                        safe_data = _redact_sensitive_data(data)
                        _LOGGER.debug("Marstek API response: %s", safe_data)

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
                                # Security: Redact sensitive data before logging
                                safe_data = _redact_sensitive_data(data)
                                _LOGGER.debug("Marstek API retry response: %s", safe_data)

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
                            error_msg = data.get("msg", "Unknown server error")
                            _LOGGER.warning(
                                "Server error (code 500): %s", error_msg
                            )
                            self._record_server_error()
                            raise MarstekServerError(f"Server error: {error_msg}")
                        
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
                        
                        # Reset circuit breaker on successful request
                        self._reset_circuit_breaker()
                        
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
                    # Exponential backoff with jitter for server errors
                    delay = min(SERVER_ERROR_RETRY_DELAY * (SERVER_ERROR_BACKOFF_MULTIPLIER ** attempt), 60)
                    jitter = delay * 0.1  # Add 10% jitter
                    total_delay = delay + jitter
                    _LOGGER.warning("Server error (attempt %d/%d), waiting %.1fs before retry...", 
                                  attempt + 1, max_retries + 1, total_delay)
                    await asyncio.sleep(total_delay)
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
        self.last_update_time: str | None = None  # Track last successful update time
        
        # Set cache TTL to match scan interval
        if hasattr(self.api, '_cache_ttl'):
            self.api._cache_ttl = scan_interval
        
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
        
        # Update cache TTL to match scan interval
        if hasattr(self.api, '_cache_ttl'):
            self.api._cache_ttl = new_interval
            
        _LOGGER.info("Scan interval updated to %d seconds (cache TTL: %d seconds)", 
                    new_interval, self.api._cache_ttl)
        
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
            
            # Update last update time
            self.last_update_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
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
            
            # Cap consecutive_no_changes to prevent overflow (1.5^20 is already very large)
            max_consecutive = 20
            safe_consecutive = min(self.consecutive_no_changes, max_consecutive)
            
            if self.consecutive_no_changes > 3:  # After 3 consecutive no-changes
                try:
                    # Calculate with bounds checking to prevent overflow
                    exponent = safe_consecutive - 3
                    
                    # Pre-check if the exponent would cause overflow before calculating
                    if exponent > 30:  # 1.5^30 is already ~191,737, much larger than any reasonable interval
                        _LOGGER.debug("Exponent too large (%d), using max interval", exponent)
                        calculated_interval = ADAPTIVE_INTERVAL_MAX
                    else:
                        try:
                            multiplier = 1.5 ** exponent
                            # Check if multiplier is valid before using it
                            if not (0 < multiplier < float('inf')):
                                calculated_interval = ADAPTIVE_INTERVAL_MAX
                            else:
                                calculated_interval = self.base_scan_interval * multiplier
                        except (OverflowError, ValueError, OSError) as calc_ex:
                            _LOGGER.debug("Calculation overflow (exponent: %d): %s", exponent, calc_ex)
                            calculated_interval = ADAPTIVE_INTERVAL_MAX
                    
                    # Ensure the result is finite and within bounds
                    if not (0 < calculated_interval < float('inf')):
                        calculated_interval = ADAPTIVE_INTERVAL_MAX
                    
                    new_interval = min(calculated_interval, ADAPTIVE_INTERVAL_MAX)
                    new_interval = max(new_interval, self.base_scan_interval)
                    
                    if new_interval != self.update_interval.total_seconds():
                        self.update_interval = timedelta(seconds=new_interval)
                        _LOGGER.debug("Adaptive interval: %d seconds (no changes: %d)", 
                                    int(new_interval), self.consecutive_no_changes)
                except (OverflowError, ValueError, OSError) as ex:
                    _LOGGER.warning("Failed to calculate adaptive interval: %s, using max", ex)
                    self.update_interval = timedelta(seconds=ADAPTIVE_INTERVAL_MAX)
                    self.consecutive_no_changes = max_consecutive  # Reset to prevent repeated errors
        else:
            # Data changed, reset to base interval
            if self.consecutive_no_changes > 0:
                self.consecutive_no_changes = 0
                self.update_interval = timedelta(seconds=self.base_scan_interval)
                _LOGGER.debug("Data changed, reset to base interval: %d seconds", 
                            self.base_scan_interval)
