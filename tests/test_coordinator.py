"""Tests for Marstek Cloud coordinator."""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, Mock, MagicMock

# Mock Home Assistant modules before importing coordinator
# We need to use types.ModuleType to create proper module objects

# Mock classes
class MockHomeAssistant:
    pass

class MockUpdateFailed(Exception):
    pass

class MockDataUpdateCoordinator:
    def __init__(self, hass, logger, name, update_interval):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
    
    def __class_getitem__(cls, item):
        return cls

class MockConfigEntry:
    pass

# Create proper module objects
ha_module = types.ModuleType('homeassistant')
ha_core_module = types.ModuleType('homeassistant.core')
ha_helpers_module = types.ModuleType('homeassistant.helpers')
ha_update_coordinator_module = types.ModuleType('homeassistant.helpers.update_coordinator')
ha_config_entries_module = types.ModuleType('homeassistant.config_entries')
ha_aiohttp_client_module = types.ModuleType('homeassistant.helpers.aiohttp_client')

# Set up module structure
ha_module.core = ha_core_module
ha_module.helpers = ha_helpers_module
ha_module.config_entries = ha_config_entries_module

ha_core_module.HomeAssistant = MockHomeAssistant
ha_helpers_module.update_coordinator = ha_update_coordinator_module
ha_helpers_module.aiohttp_client = ha_aiohttp_client_module
ha_update_coordinator_module.UpdateFailed = MockUpdateFailed
ha_update_coordinator_module.DataUpdateCoordinator = MockDataUpdateCoordinator
ha_config_entries_module.ConfigEntry = MockConfigEntry
ha_aiohttp_client_module.async_get_clientsession = MagicMock()

# Register modules
sys.modules['homeassistant'] = ha_module
sys.modules['homeassistant.core'] = ha_core_module
sys.modules['homeassistant.helpers'] = ha_helpers_module
sys.modules['homeassistant.helpers.update_coordinator'] = ha_update_coordinator_module
sys.modules['homeassistant.config_entries'] = ha_config_entries_module
sys.modules['homeassistant.helpers.aiohttp_client'] = ha_aiohttp_client_module

import pytest
from aiohttp import ClientSession
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.marstek_cloud.coordinator import (MarstekAPI, MarstekAPIError,
                                       MarstekAuthenticationError,
                                       MarstekCoordinator,
                                       MarstekPermissionError)


@pytest.fixture
def mock_session():
    """Mock aiohttp session."""
    return Mock(spec=ClientSession)


@pytest.fixture
def api_client(mock_session):
    """Create MarstekAPI instance for testing."""
    return MarstekAPI(mock_session, "test@example.com", "password123")


class TestMarstekAPI:
    """Test MarstekAPI class."""

    def test_init(self, api_client):
        """Test API client initialization."""
        assert api_client._email == "test@example.com"
        assert api_client._password == "password123"
        assert api_client._token is None
        # Check default cache_ttl is 60
        assert api_client._cache_ttl == 60

    def test_init_with_custom_cache_ttl(self, mock_session):
        """Test API client initialization with custom cache_ttl."""
        api_client = MarstekAPI(mock_session, "test@example.com", "password123", cache_ttl=120)
        assert api_client._cache_ttl == 120

    @pytest.mark.asyncio
    async def test_get_token_success(self, api_client, mock_session):
        """Test successful token retrieval."""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"token": "test_token_123", "code": "2"})

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_context

        await api_client._get_token()

        assert api_client._token == "test_token_123"
        mock_session.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_token_failure(self, api_client, mock_session):
        """Test token retrieval failure."""
        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"error": "Invalid credentials", "code": "-1"})

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_session.post.return_value = mock_context

        with pytest.raises(MarstekAuthenticationError):
            await api_client._get_token()

    @pytest.mark.asyncio
    async def test_get_devices_success(self, api_client, mock_session):
        """Test successful device retrieval."""
        # Mock token with expiration
        from datetime import datetime, timedelta
        api_client._token = "test_token_123"
        api_client._token_expires_at = datetime.now() + timedelta(hours=1)

        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(
            return_value={
                "data": [{"devid": "device1", "name": "Battery 1", "soc": 85}],
                "code": 1
            }
        )

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_session.get.return_value = mock_context

        devices = await api_client.get_devices()

        assert len(devices) == 1
        assert devices[0]["devid"] == "device1"
        assert devices[0]["soc"] == 85

    @pytest.mark.asyncio
    async def test_get_devices_permission_error(self, api_client, mock_session):
        """Test permission error handling."""
        from datetime import datetime, timedelta
        api_client._token = "test_token_123"
        api_client._token_expires_at = datetime.now() + timedelta(hours=1)

        mock_response = Mock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"code": "8"})

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_session.get.return_value = mock_context

        with pytest.raises(MarstekPermissionError):
            await api_client.get_devices()


class TestMarstekCoordinator:
    """Test MarstekCoordinator class."""

    @pytest.fixture
    def mock_hass(self):
        """Mock Home Assistant instance."""
        return Mock(spec=HomeAssistant)

    @pytest.fixture
    def coordinator(self, mock_hass, api_client):
        """Create MarstekCoordinator instance for testing."""
        return MarstekCoordinator(mock_hass, api_client, 60)

    def test_init(self, coordinator, mock_hass, api_client):
        """Test coordinator initialization."""
        assert coordinator.hass == mock_hass
        assert coordinator.api == api_client
        assert coordinator.last_latency is None
        assert coordinator.base_scan_interval == 60
        # Check that cache_ttl is set to match scan_interval
        assert api_client._cache_ttl == 60
        # Check last_update_time is initialized
        assert coordinator.last_update_time is None

    def test_update_scan_interval(self, coordinator, api_client):
        """Test updating scan interval also updates cache TTL."""
        coordinator.update_scan_interval(120)
        assert coordinator.base_scan_interval == 120
        assert api_client._cache_ttl == 120
        assert coordinator.update_interval.total_seconds() == 120

    @pytest.mark.asyncio
    async def test_async_update_data_success(self, coordinator, api_client):
        """Test successful data update."""
        test_devices = [
            {"devid": "device1", "name": "Battery 1", "soc": 85},
            {"devid": "device2", "name": "Battery 2", "soc": 92},
        ]

        api_client.get_devices = AsyncMock(return_value=test_devices)

        result = await coordinator._async_update_data()

        assert result == test_devices
        assert coordinator.last_latency is not None
        assert coordinator.last_latency >= 0
        # Check that last_update_time is set
        assert coordinator.last_update_time is not None
        from datetime import datetime
        # Verify the format
        datetime.strptime(coordinator.last_update_time, "%Y-%m-%d %H:%M:%S")

    @pytest.mark.asyncio
    async def test_async_update_data_permission_error(self, coordinator, api_client):
        """Test data update with permission error."""
        api_client.get_devices = AsyncMock(
            side_effect=MarstekPermissionError("No access")
        )

        with pytest.raises(UpdateFailed, match="Permission error"):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_async_update_data_api_error(self, coordinator, api_client):
        """Test data update with API error."""
        api_client.get_devices = AsyncMock(side_effect=MarstekAPIError("API error"))

        with pytest.raises(UpdateFailed, match="API error"):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_cache_validation(self, api_client):
        """Test cache validation uses cache_ttl."""
        from datetime import datetime, timedelta
        
        # Set cache_ttl to 60
        api_client._cache_ttl = 60
        
        # Set cached devices
        api_client._cached_devices = [{"devid": "test"}]
        
        # Fresh cache should be valid
        api_client._cache_timestamp = datetime.now()
        assert api_client._is_cache_valid() is True
        
        # Cache older than TTL should be invalid
        api_client._cache_timestamp = datetime.now() - timedelta(seconds=61)
        assert api_client._is_cache_valid() is False
        
        # Cache just within TTL should be valid
        api_client._cache_timestamp = datetime.now() - timedelta(seconds=59)
        assert api_client._is_cache_valid() is True
