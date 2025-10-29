"""Real-world integration tests for Marstek Cloud API.

These tests require actual API credentials and should be run separately
from the unit tests. They test against the real Marstek Cloud API.

To run these tests:
    python -m pytest tests/test_integration.py -v -s

Make sure you have a .env file with:
    MARSTEK_EMAIL=your_email@example.com
    MARSTEK_PASSWORD=your_password
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import Mock

import pytest
import pytest_asyncio
from dotenv import load_dotenv

from custom_components.marstek_cloud.coordinator import MarstekAPI, MarstekCoordinator

# Load environment variables from .env file
load_dotenv()

# Skip all tests in this module if credentials are not available
pytestmark = [
    pytest.mark.skipif(
        not os.getenv("MARSTEK_EMAIL") or not os.getenv("MARSTEK_PASSWORD"),
        reason="Real API credentials not available in environment",
    ),
    pytest.mark.integration,
]


@pytest_asyncio.fixture
async def real_api_session():
    """Create a real aiohttp session for integration testing."""
    import aiohttp

    session = aiohttp.ClientSession()
    yield session
    await session.close()


@pytest_asyncio.fixture
async def real_api_client(real_api_session):
    """Create MarstekAPI instance with real credentials."""
    email = os.getenv("MARSTEK_EMAIL")
    password = os.getenv("MARSTEK_PASSWORD")
    return MarstekAPI(real_api_session, email, password)


@pytest_asyncio.fixture
async def real_coordinator(real_api_client):
    """Create MarstekCoordinator instance for integration testing."""
    mock_hass = Mock()
    return MarstekCoordinator(mock_hass, real_api_client, 60)


class TestMarstekAPIIntegration:
    """Integration tests against real Marstek Cloud API."""

    @pytest.mark.asyncio
    async def test_real_authentication(self, real_api_client):
        """Test authentication with real API credentials."""
        # This should not raise an exception
        await real_api_client._get_token()
        assert real_api_client._token is not None
        assert len(real_api_client._token) > 0

    @pytest.mark.asyncio
    async def test_real_device_fetch(self, real_api_client):
        """Test fetching devices from real API."""
        devices = await real_api_client.get_devices()
        
        # Should return a list
        assert isinstance(devices, list)
        
        # If devices are found, they should have expected structure
        if devices:
            device = devices[0]
            assert isinstance(device, dict)
            # Check for common device fields
            assert "devid" in device
            assert "name" in device
            print(f"Found {len(devices)} devices")
            for device in devices:
                print(f"  - {device.get('name', 'Unknown')} (ID: {device.get('devid', 'Unknown')})")

    @pytest.mark.asyncio
    async def test_real_coordinator_update(self, real_coordinator):
        """Test coordinator data update with real API."""
        devices = await real_coordinator._async_update_data()
        
        # Should return a list
        assert isinstance(devices, list)
        
        # Check coordinator state
        assert real_coordinator.last_latency is not None
        assert real_coordinator.last_latency >= 0
        
        print(f"API latency: {real_coordinator.last_latency}ms")
        print(f"Fetched {len(devices)} devices")

    @pytest.mark.asyncio
    async def test_real_api_performance(self, real_api_client):
        """Test API performance and response times."""
        import time
        
        # Test multiple requests to check consistency
        latencies = []
        for i in range(3):
            start = time.perf_counter()
            devices = await real_api_client.get_devices()
            latency = (time.perf_counter() - start) * 1000
            latencies.append(latency)
            print(f"Request {i+1}: {latency:.1f}ms, {len(devices)} devices")
        
        avg_latency = sum(latencies) / len(latencies)
        print(f"Average latency: {avg_latency:.1f}ms")
        
        # All requests should succeed
        assert all(latency > 0 for latency in latencies)
        # Average latency should be reasonable (less than 10 seconds)
        assert avg_latency < 10000

    @pytest.mark.asyncio
    async def test_real_api_error_handling(self, real_api_client):
        """Test error handling with real API."""
        # Test with invalid token (should trigger refresh)
        original_token = real_api_client._token
        real_api_client._token = "invalid_token"
        
        # This should work because it will refresh the token
        devices = await real_api_client.get_devices()
        assert isinstance(devices, list)
        
        # Token should be refreshed
        assert real_api_client._token != "invalid_token"
        assert real_api_client._token is not None

    @pytest.mark.asyncio
    async def test_real_device_data_structure(self, real_api_client):
        """Test the structure of real device data."""
        devices = await real_api_client.get_devices()
        
        if not devices:
            pytest.skip("No devices found in real API")
        
        device = devices[0]
        print(f"Sample device data: {device}")
        
        # Check for expected fields
        expected_fields = ["devid", "name"]
        for field in expected_fields:
            assert field in device, f"Missing field: {field}"
        
        # Check for sensor data fields
        sensor_fields = ["soc", "charge", "discharge", "load", "profit", "version", "sn", "report_time"]
        found_sensor_fields = [field for field in sensor_fields if field in device]
        print(f"Found sensor fields: {found_sensor_fields}")
        
        # At least some sensor data should be present
        assert len(found_sensor_fields) > 0, "No sensor data fields found in device"


@pytest.mark.asyncio
async def test_real_api_connection_robustness():
    """Test API connection robustness with real credentials."""
    import aiohttp
    
    email = os.getenv("MARSTEK_EMAIL")
    password = os.getenv("MARSTEK_PASSWORD")
    
    async with aiohttp.ClientSession() as session:
        api = MarstekAPI(session, email, password)
        
        # Test multiple rapid requests
        tasks = []
        for i in range(5):
            task = asyncio.create_task(api.get_devices())
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All requests should succeed
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                pytest.fail(f"Request {i+1} failed: {result}")
            assert isinstance(result, list)
        
        print(f"Successfully completed {len(results)} concurrent API requests")


if __name__ == "__main__":
    # Allow running this file directly for quick testing
    import asyncio
    from dotenv import load_dotenv
    
    load_dotenv()
    
    async def main():
        """Run a quick integration test."""
        import aiohttp
        from custom_components.marstek_cloud.coordinator import MarstekAPI
        
        email = os.getenv("MARSTEK_EMAIL")
        password = os.getenv("MARSTEK_PASSWORD")
        
        if not email or not password:
            print("❌ Please set MARSTEK_EMAIL and MARSTEK_PASSWORD in .env file")
            return
        
        print("🚀 Testing Marstek Cloud API integration...")
        
        async with aiohttp.ClientSession() as session:
            api = MarstekAPI(session, email, password)
            
            try:
                print("📡 Fetching devices...")
                devices = await api.get_devices()
                print(f"✅ Successfully fetched {len(devices)} devices")
                
                for device in devices:
                    name = device.get("name", "Unknown")
                    devid = device.get("devid", "Unknown")
                    soc = device.get("soc", "N/A")
                    print(f"  🔋 {name} (ID: {devid}) - SOC: {soc}%")
                
            except Exception as e:
                print(f"❌ Error: {e}")
    
    asyncio.run(main())
