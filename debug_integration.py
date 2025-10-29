#!/usr/bin/env python3
"""Debug script for Marstek Cloud integration issues.

This script helps diagnose server errors and performance issues.
"""

import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add the custom_components directory to the path
sys.path.insert(0, str(Path(__file__).parent / "custom_components"))

from marstek_cloud.coordinator import MarstekAPI
import aiohttp

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
_LOGGER = logging.getLogger(__name__)

async def test_api_connection(email: str, password: str):
    """Test the API connection and diagnose issues."""
    _LOGGER.info("Starting API connection test...")
    
    connector = aiohttp.TCPConnector(
        limit=10,
        limit_per_host=2,
        ttl_dns_cache=300,
        use_dns_cache=True,
        keepalive_timeout=30,
        enable_cleanup_closed=True,
        force_close=False,
        resolver=aiohttp.AsyncResolver(nameservers=['8.8.8.8', '1.1.1.1'])
    )
    
    timeout = aiohttp.ClientTimeout(
        total=30,
        connect=10,
        sock_read=15,
        sock_connect=10
    )
    
    async with aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        headers={
            'User-Agent': 'HomeAssistant-MarstekCloud/0.5.0',
            'Accept': 'application/json',
            'Connection': 'keep-alive'
        }
    ) as session:
        api = MarstekAPI(session, email, password)
        
        try:
            # Test multiple requests to see error patterns
            for i in range(5):
                _LOGGER.info(f"Test request {i+1}/5...")
                start_time = datetime.now()
                
                try:
                    devices = await api.get_devices()
                    duration = (datetime.now() - start_time).total_seconds()
                    _LOGGER.info(f"Request {i+1} successful in {duration:.2f}s, got {len(devices)} devices")
                    
                    # Log device info
                    for device in devices:
                        _LOGGER.info(f"Device: {device.get('name', 'Unknown')} - SOC: {device.get('soc', 'N/A')}%")
                        
                except Exception as e:
                    duration = (datetime.now() - start_time).total_seconds()
                    _LOGGER.error(f"Request {i+1} failed after {duration:.2f}s: {e}")
                
                # Wait between requests
                if i < 4:
                    await asyncio.sleep(2)
                    
        except Exception as e:
            _LOGGER.error(f"API test failed: {e}")
        finally:
            await api.close()

async def main():
    """Main function."""
    print("Marstek Cloud Integration Debug Tool")
    print("=" * 40)
    
    # Get credentials from user
    email = input("Enter your Marstek email: ").strip()
    password = input("Enter your Marstek password: ").strip()
    
    if not email or not password:
        print("Error: Email and password are required")
        return
    
    await test_api_connection(email, password)

if __name__ == "__main__":
    asyncio.run(main())
