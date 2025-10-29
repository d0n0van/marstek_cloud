"""Tests for Marstek Cloud coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from aiohttp import ClientSession
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from marstek_cloud.coordinator import (MarstekAPI, MarstekAPIError,
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
        mock_response.json = AsyncMock(return_value={"error": "Invalid credentials", "code": "401"})

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
        mock_response.json = AsyncMock(return_value={"code": "8", "msg": "Permission denied"})

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_session.get.return_value = mock_context

        with pytest.raises(MarstekAuthenticationError):
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

    @pytest.mark.asyncio
    async def test_async_update_data_permission_error(self, coordinator, api_client):
        """Test data update with permission error."""
        api_client.get_devices = AsyncMock(
            side_effect=MarstekAuthenticationError("No access")
        )

        with pytest.raises(UpdateFailed, match="Authentication error"):
            await coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_async_update_data_api_error(self, coordinator, api_client):
        """Test data update with API error."""
        api_client.get_devices = AsyncMock(side_effect=MarstekAPIError("API error"))

        with pytest.raises(UpdateFailed, match="API error"):
            await coordinator._async_update_data()
