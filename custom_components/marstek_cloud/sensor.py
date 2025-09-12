from datetime import datetime
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPower,
    UnitOfTime,
    CURRENCY_EURO,
)
from .const import DOMAIN

# Main battery data sensors
SENSOR_TYPES = {
    "soc": {"name": "State of Charge", "unit": PERCENTAGE},
    "charge": {"name": "Charge Power", "unit": UnitOfPower.WATT},
    "discharge": {"name": "Discharge Power", "unit": UnitOfPower.WATT},
    "load": {"name": "Load", "unit": UnitOfPower.WATT},
    "profit": {"name": "Profit", "unit": CURRENCY_EURO},
    "version": {"name": "Firmware Version", "unit": None},
    "sn": {"name": "Serial Number", "unit": None},
    "report_time": {"name": "Report Time", "unit": UnitOfTime.SECONDS},
}

# Diagnostic sensors for integration health
DIAGNOSTIC_SENSORS = {
    "last_update": {"name": "Last Update", "unit": None},
    "api_latency": {"name": "API Latency", "unit": "ms"},
    "connection_status": {"name": "Connection Status", "unit": None},
}


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Marstek sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for device in coordinator.data:
        # Add main battery data sensors
        for key, meta in SENSOR_TYPES.items():
            entities.append(MarstekSensor(coordinator, device, key, meta))

        # Add diagnostic sensors
        for key, meta in DIAGNOSTIC_SENSORS.items():
            entities.append(MarstekDiagnosticSensor(coordinator, device, key, meta))

    async_add_entities(entities)


class MarstekBaseSensor(SensorEntity):
    """Base class for Marstek sensors with shared device info."""

    def __init__(self, coordinator, device, key, meta):
        self.coordinator = coordinator
        self.devid = device["devid"]
        self.device_data = device
        self.key = key
        self._attr_name = f"{device['name']} {meta['name']}"
        self._attr_unique_id = f"{self.devid}_{key}"
        self._attr_native_unit_of_measurement = meta["unit"]

    @property
    def device_info(self):
        """Return metadata for the device registry."""
        return {
            "identifiers": {(DOMAIN, self.devid)},
            "name": self.device_data["name"],
            "manufacturer": "Marstek",
            "model": self.device_data.get("type", "Unknown"),
            "sw_version": str(self.device_data.get("version", "")),
            "serial_number": self.device_data.get("sn", ""),
        }


class MarstekSensor(MarstekBaseSensor):
    """Sensor for actual battery data."""

    @property
    def native_value(self):
        """Return the current value of the sensor."""
        for dev in self.coordinator.data:
            if dev["devid"] == self.devid:
                return dev.get(self.key)
        return None

    async def async_update(self):
        """Manually trigger an update."""
        await self.coordinator.async_request_refresh()


class MarstekDiagnosticSensor(MarstekBaseSensor):
    """Sensor for integration diagnostics."""

    @property
    def native_value(self):
        """Return the diagnostic value."""
        if self.key == "last_update":
            if self.coordinator.last_update_success:
                return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return None

        elif self.key == "api_latency":
            return getattr(self.coordinator, "last_latency", None)

        elif self.key == "connection_status":
            return "online" if self.coordinator.last_update_success else "offline"

        return None
