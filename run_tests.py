#!/usr/bin/env python3
"""Test runner for Marstek Cloud integration with mocked Home Assistant dependencies."""

import sys
import os
import types
from unittest.mock import Mock

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Create comprehensive Home Assistant mocks
def create_ha_mocks():
    """Create comprehensive Home Assistant mocks for testing."""
    
    # Mock constants
    ha_const = types.ModuleType('homeassistant.const')
    ha_const.CURRENCY_EURO = '€'
    ha_const.PERCENTAGE = '%'
    ha_const.UnitOfEnergy = types.ModuleType('UnitOfEnergy')
    ha_const.UnitOfEnergy.KILO_WATT_HOUR = 'kWh'
    ha_const.UnitOfPower = types.ModuleType('UnitOfPower')
    ha_const.UnitOfPower.WATT = 'W'
    ha_const.UnitOfElectricCurrent = types.ModuleType('UnitOfElectricCurrent')
    ha_const.UnitOfElectricCurrent.AMPERE = 'A'
    ha_const.UnitOfElectricPotential = types.ModuleType('UnitOfElectricPotential')
    ha_const.UnitOfElectricPotential.VOLT = 'V'
    
    # Mock sensor components
    ha_sensor = types.ModuleType('homeassistant.components.sensor')
    class MockSensorEntity:
        pass
    ha_sensor.SensorEntity = MockSensorEntity
    
    # Mock config entries
    ha_config_entries = types.ModuleType('homeassistant.config_entries')
    class MockConfigEntry:
        def __init__(self):
            self.data = {}
            self.options = {}
    ha_config_entries.ConfigEntry = MockConfigEntry
    
    # Mock core
    ha_core = types.ModuleType('homeassistant.core')
    ha_core.HomeAssistant = Mock
    ha_core.callback = lambda x: x  # Identity decorator
    
    # Mock helpers
    ha_helpers = types.ModuleType('homeassistant.helpers')
    
    # Mock aiohttp_client
    ha_aiohttp_client = types.ModuleType('homeassistant.helpers.aiohttp_client')
    ha_aiohttp_client.async_get_clientsession = Mock(return_value=Mock())
    
    # Mock update_coordinator
    ha_update_coordinator = types.ModuleType('homeassistant.helpers.update_coordinator')
    class MockUpdateFailed(Exception):
        pass
    class MockDataUpdateCoordinator:
        def __init__(self, hass, logger, name, update_interval):
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
        def __class_getitem__(cls, item):
            return cls  # Make it subscriptable
    ha_update_coordinator.DataUpdateCoordinator = MockDataUpdateCoordinator
    ha_update_coordinator.UpdateFailed = MockUpdateFailed
    
    ha_helpers.aiohttp_client = ha_aiohttp_client
    ha_helpers.update_coordinator = ha_update_coordinator
    
    # Mock main homeassistant module
    ha_module = types.ModuleType('homeassistant')
    ha_module.core = ha_core
    ha_module.const = ha_const
    ha_module.components = types.ModuleType('homeassistant.components')
    ha_module.components.sensor = ha_sensor
    ha_module.config_entries = ha_config_entries
    ha_module.helpers = ha_helpers
    
    # Register all modules
    sys.modules['homeassistant'] = ha_module
    sys.modules['homeassistant.core'] = ha_core
    sys.modules['homeassistant.const'] = ha_const
    sys.modules['homeassistant.components'] = ha_module.components
    sys.modules['homeassistant.components.sensor'] = ha_sensor
    sys.modules['homeassistant.config_entries'] = ha_config_entries
    sys.modules['homeassistant.helpers'] = ha_helpers
    sys.modules['homeassistant.helpers.aiohttp_client'] = ha_aiohttp_client
    sys.modules['homeassistant.helpers.update_coordinator'] = ha_update_coordinator

if __name__ == "__main__":
    # Create mocks before importing anything
    create_ha_mocks()
    
    # Now run pytest
    import subprocess
    import pytest
    
    # Run the tests
    exit_code = pytest.main([
        'tests/',
        '-v',
        '--tb=short',
        '--no-cov'  # Disable coverage for now
    ])
    
    sys.exit(exit_code)