"""Marstek Cloud API coordinator and data fetching."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

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

# Error classification
class ErrorType(Enum):
    """Types of API errors for better handling."""
    TEMPORARY = "temporary"  # 502, 503, rate limits, server errors
    AUTHENTICATION = "auth"  # 401, 403, token issues
    DATA = "data"  # JSON parsing, data validation
    PERMANENT = "permanent"  # 404, invalid requests

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 30]  # Progressive delays in seconds


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


class MarstekTemporaryError(MarstekAPIError):
    """Temporary error that should be retried."""

    pass


class MarstekDataError(MarstekAPIError):
    """Data parsing or processing error."""

    pass


class SharedRateLimiter:
    """Shared rate limiter for all API calls."""
    
    def __init__(self):
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        self._last_request_time = 0
        self._min_request_interval = 1.0  # Minimum 1 second between requests
        
    async def acquire(self):
        """Acquire rate limiter and wait if necessary."""
        await self._semaphore.acquire()
        
        # Ensure minimum interval between requests
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - time_since_last)
        
        self._last_request_time = time.time()
        
    def release(self):
        """Release the rate limiter."""
        self._semaphore.release()


class MarstekAPI:
    """Handle API communication with Marstek Cloud."""

    def __init__(
        self, session: aiohttp.ClientSession, email: str, password: str, 
        rate_limiter: Optional[SharedRateLimiter] = None
    ) -> None:
        """Initialize the Marstek API client.

        Args:
            session: aiohttp session for HTTP requests.
            email: User email for authentication.
            password: User password for authentication.
            rate_limiter: Shared rate limiter instance.
        """
        self._session = session
        self._email = email
        self._password = password
        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._rate_limiter = rate_limiter or SharedRateLimiter()
        
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

    def _classify_error(self, status_code: int, response_data: dict) -> ErrorType:
        """Classify API errors for appropriate handling."""
        # HTTP status code classification
        if status_code >= 500:
            return ErrorType.TEMPORARY
        elif status_code in [401, 403]:
            return ErrorType.AUTHENTICATION
        elif status_code == 404:
            return ErrorType.PERMANENT
        
        # API response code classification
        api_code = response_data.get('code')
        if api_code == 500:
            return ErrorType.TEMPORARY
        elif api_code in ["-1", "401", "403"]:
            return ErrorType.AUTHENTICATION
        elif api_code == "5":
            return ErrorType.TEMPORARY
        elif api_code == "8":
            return ErrorType.AUTHENTICATION
        else:
            return ErrorType.PERMANENT

    def _handle_classified_error(self, error_type: ErrorType, status_code: int, 
                               response_data: dict, original_exception: Exception = None):
        """Handle errors based on their classification."""
        if error_type == ErrorType.TEMPORARY:
            _LOGGER.warning("Temporary API error (status %d, code %s): %s", 
                          status_code, response_data.get('code'), 
                          response_data.get('msg', 'Unknown error'))
            raise MarstekTemporaryError(f"Temporary error: {response_data.get('msg', 'Unknown error')}")
        elif error_type == ErrorType.AUTHENTICATION:
            _LOGGER.error("Authentication error (status %d, code %s): %s", 
                        status_code, response_data.get('code'),
                        response_data.get('msg', 'Authentication failed'))
            raise MarstekAuthenticationError(f"Auth error: {response_data.get('msg', 'Authentication failed')}")
        elif error_type == ErrorType.DATA:
            _LOGGER.error("Data processing error: %s", original_exception)
            raise MarstekDataError(f"Data error: {original_exception}")
        else:  # PERMANENT
            _LOGGER.error("Permanent API error (status %d, code %s): %s", 
                        status_code, response_data.get('code'),
                        response_data.get('msg', 'Unknown error'))
            raise MarstekAPIError(f"Permanent API error: {response_data.get('msg', 'Unknown error')}")

    async def _retry_with_backoff(self, func, *args, **kwargs):
        """Retry function with exponential backoff for temporary errors."""
        last_exception = None
        
        for attempt in range(MAX_RETRIES + 1):
            try:
                return await func(*args, **kwargs)
            except MarstekTemporaryError as e:
                last_exception = e
                if attempt < MAX_RETRIES:
                    delay = RETRY_DELAYS[attempt]
                    _LOGGER.warning("Temporary error (attempt %d/%d): %s. Retrying in %ds...", 
                                  attempt + 1, MAX_RETRIES + 1, e, delay)
                    await asyncio.sleep(delay)
                else:
                    _LOGGER.error("Max retries exceeded for temporary error: %s", e)
            except (MarstekAPIError, MarstekDataError) as e:
                # Don't retry for non-temporary errors
                raise e
            except Exception as e:
                last_exception = e
                _LOGGER.error("Unexpected error during retry attempt %d: %s", attempt + 1, e)
                if attempt >= MAX_RETRIES:
                    break
        
        raise last_exception

    def _process_device_data(self, device: dict) -> dict:
        """Safely process device data with error handling."""
        processed = device.copy()
        
        # Safe timestamp conversion
        if 'report_time' in processed and processed['report_time']:
            try:
                # Convert Unix timestamp to datetime
                timestamp = int(processed['report_time'])
                processed['report_time_dt'] = datetime.fromtimestamp(timestamp)
            except (ValueError, TypeError, OverflowError) as e:
                _LOGGER.warning("Timestamp conversion error for device %s: %s", 
                              device.get('devid', 'unknown'), e)
                processed['report_time_dt'] = None
        
        # Safe numeric conversions
        numeric_fields = ['soc', 'charge', 'discharge', 'load', 'pv', 'profit']
        for field in numeric_fields:
            if field in processed and processed[field] is not None:
                try:
                    processed[field] = float(processed[field])
                except (ValueError, TypeError) as e:
                    _LOGGER.warning("Numeric conversion error for %s.%s: %s", 
                                  device.get('devid', 'unknown'), field, e)
                    processed[field] = 0.0
        
        return processed

    async def _get_token(self) -> None:
        """Obtain authentication token from Marstek API with rate limiting and error handling.

        Raises:
            MarstekAuthenticationError: If authentication fails.
            MarstekTemporaryError: If temporary server error occurs.
        """
        await self._rate_limiter.acquire()
        try:
            md5_pwd = hashlib.md5(self._password.encode()).hexdigest()
            params = {"pwd": md5_pwd, "mailbox": self._email}

            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            async with self._session.post(API_LOGIN, params=params, timeout=timeout) as resp:
                try:
                    data = await resp.json()
                except Exception as e:
                    raise MarstekDataError(f"JSON parsing error: {e}")

                # Classify and handle errors
                if resp.status != 200:
                    error_type = self._classify_error(resp.status, data)
                    self._handle_classified_error(error_type, resp.status, data)

                if data.get("code") != "2" or "token" not in data:
                    error_type = self._classify_error(resp.status, data)
                    self._handle_classified_error(error_type, resp.status, data)

                self._token = data["token"]
                # Set token expiration (assume 1 hour, refresh 5 minutes before)
                self._token_expires_at = datetime.now() + timedelta(hours=1)
                _LOGGER.info("Successfully obtained new API token")

        except aiohttp.ClientError as ex:
            raise MarstekTemporaryError(f"Network error during login: {ex}") from ex
        except asyncio.TimeoutError as ex:
            raise MarstekTemporaryError("Login request timed out") from ex
        finally:
            self._rate_limiter.release()

    async def get_devices(self) -> list[dict[str, Any]]:
        """Fetch device list from Marstek API with improved error handling and retry logic.

        Returns:
            List of device dictionaries.

        Raises:
            MarstekPermissionError: If no access permission.
            MarstekTemporaryError: If temporary server error occurs.
            MarstekDataError: If data processing fails.
        """
        return await self._retry_with_backoff(self._get_devices_impl)

    async def _get_devices_impl(self) -> list[dict[str, Any]]:
        """Implementation of get_devices with rate limiting and error handling."""
        # Check if we have valid cached data
        if self._is_cache_valid():
            _LOGGER.debug("Returning cached device data")
            return self._cached_devices

        # Check if token needs refresh
        if not self._is_token_valid() or self._should_refresh_token():
            _LOGGER.debug("Token invalid or needs refresh, getting new token")
            await self._get_token()

        await self._rate_limiter.acquire()
        try:
            params = {"token": self._token}
            timeout = aiohttp.ClientTimeout(total=API_TIMEOUT)
            
            async with self._session.get(API_DEVICES, params=params, timeout=timeout) as resp:
                try:
                    data = await resp.json()
                except Exception as e:
                    raise MarstekDataError(f"JSON parsing error: {e}")

                _LOGGER.debug("Marstek API response: %s", data)

                # Classify and handle errors
                if resp.status != 200:
                    error_type = self._classify_error(resp.status, data)
                    self._handle_classified_error(error_type, resp.status, data)

                # Handle API response codes
                api_code = data.get("code")
                if api_code != 1:  # Success code
                    error_type = self._classify_error(resp.status, data)
                    self._handle_classified_error(error_type, resp.status, data)

                if "data" not in data:
                    raise MarstekDataError(f"Invalid API response structure: {data}")

                devices = data["data"]
                
                # Process device data safely
                processed_devices = []
                for device in devices:
                    try:
                        processed_device = self._process_device_data(device)
                        processed_devices.append(processed_device)
                    except Exception as e:
                        _LOGGER.warning("Data processing warning for device %s: %s", 
                                      device.get('devid', 'unknown'), e)
                        # Continue with other devices
                        processed_devices.append(device)
                
                # Cache the data
                self._cached_devices = processed_devices
                self._cache_timestamp = datetime.now()
                
                # Check if data has changed for adaptive intervals
                current_hash = self._get_data_hash(processed_devices)
                if self._last_data_hash and current_hash == self._last_data_hash:
                    _LOGGER.debug("Device data unchanged, will use longer interval")
                self._last_data_hash = current_hash

                return processed_devices

        except aiohttp.ClientError as ex:
            raise MarstekTemporaryError(f"Network error during device fetch: {ex}") from ex
        except asyncio.TimeoutError as ex:
            raise MarstekTemporaryError("Device fetch request timed out") from ex
        finally:
            self._rate_limiter.release()


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
        """Fetch latest data from Marstek API with improved error handling.

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

        except MarstekTemporaryError as ex:
            _LOGGER.warning("Temporary API error, will retry: %s", ex)
            # Don't raise UpdateFailed for temporary errors - let retry logic handle it
            return self.data or {"devices": []}
        except MarstekAuthenticationError as ex:
            _LOGGER.error("Authentication error: %s", ex)
            raise UpdateFailed(f"Authentication error: {ex}") from ex
        except MarstekDataError as ex:
            _LOGGER.error("Data processing error: %s", ex)
            raise UpdateFailed(f"Data error: {ex}") from ex
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
