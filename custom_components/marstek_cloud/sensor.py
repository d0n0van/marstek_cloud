from datetime import datetime
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPower,
    UnitOfTime,
    UnitOfEnergy,
    CURRENCY_EURO,
)
from .const import DOMAIN, DEFAULT_CAPACITY_KWH
import logging

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
    "total_charge": {"name": "Total Charge", "unit": UnitOfEnergy.KILO_WATT_HOUR},
}

# Diagnostic sensors for integration health
DIAGNOSTIC_SENSORS = {
    "last_update": {"name": "Last Update", "unit": None},
    "api_latency": {"name": "API Latency", "unit": "ms"},
    "connection_status": {"name": "Connection Status", "unit": None},
}

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Marstek sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    _LOGGER.debug("Coordinator data: %s", coordinator.data)

    for device in coordinator.data:
        _LOGGER.debug("Processing device: %s", device)

        # Add main battery data sensors
        for key, meta in SENSOR_TYPES.items():
            entities.append(MarstekSensor(coordinator, device, key, meta))

        # Add total charge sensor
        entities.append(MarstekChargeSensor(coordinator, device, entry))

        # Add diagnostic sensors
        for key, meta in DIAGNOSTIC_SENSORS.items():
            entities.append(MarstekDiagnosticSensor(coordinator, device, key, meta))

    # Add total charge across all devices sensor
    entities.append(MarstekTotalChargeSensor(coordinator))
    # Add total power across all devices sensor
    entities.append(MarstekTotalPowerSensor(coordinator))

    async_add_entities(entities)


class MarstekBaseSensor(SensorEntity):
    """Base class for Marstek sensors with shared device info."""

    def __init__(self, coordinator, device, key, meta):
        self.coordinator = coordinator
        self.devid = device["devid"]
        self.device_data = device
        self.key = key
        self._attr_name = f"{device['name']} {meta['name']}"
        self._attr_unique_id = f"{self.devid}_{self.key}"  # Ensure unique ID includes device ID and sensor key
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


class MarstekChargeSensor(MarstekBaseSensor):
    """Sensor to calculate total charge in kWh."""

    def __init__(self, coordinator, device, config_entry):
        super().__init__(coordinator, device, "total_charge", SENSOR_TYPES["total_charge"])
        self.config_entry = config_entry
        self._attr_unique_id = f"{self.devid}_sensor_{self.key}"  # Ensure unique ID includes device ID and sensor key

    @property
    def native_value(self):
        """Return the total charge in kWh."""
        device_data = next((dev for dev in self.coordinator.data if dev["devid"] == self.devid), None)
        if not device_data:
            return None
        soc = device_data.get("soc", 0)
        capacity_kwh = self.config_entry.options.get(f"{self.devid}_capacity_kwh", DEFAULT_CAPACITY_KWH)
        return round((soc / 100) * capacity_kwh, 2)

    @property
    def extra_state_attributes(self):
        capacity_kwh = self.config_entry.options.get(f"{self.devid}_capacity_kwh", DEFAULT_CAPACITY_KWH)
        return {
            "capacity_kwh": capacity_kwh,
        }


class MarstekTotalChargeSensor(SensorEntity):
    """Sensor to calculate the total charge across all devices."""

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._attr_name = "Total Charge Across Devices"
        self._attr_unique_id = f"total_charge_all_devices_{id(self.coordinator)}"  # Ensure unique ID for total charge sensor
        self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    @property
    def native_value(self):
        """Return the total charge across all devices."""
        total_charge = 0
        for device in self.coordinator.data:
            soc = device.get("soc", 0)
            capacity_kwh = device.get("capacity_kwh", DEFAULT_CAPACITY_KWH)
            total_charge += (soc / 100) * capacity_kwh
        return round(total_charge, 2)

    @property
    def extra_state_attributes(self):
        return {
            "device_count": len(self.coordinator.data),
        }


class MarstekTotalPowerSensor(SensorEntity):
    """Sensor to calculate the total charge and discharge power across all devices."""

    def __init__(self, coordinator):
        self.coordinator = coordinator
        self._attr_name = "Total Power Across Devices"
        self._attr_unique_id = f"total_power_all_devices_{id(self.coordinator)}"  # Ensure unique ID for total power sensor
        self._attr_native_unit_of_measurement = UnitOfPower.WATT

    @property
    def native_value(self):
        """Return the total power (charge - discharge) across all devices."""
        total_power = 0
        for device in self.coordinator.data:
            charge_power = device.get("charge", 0)
            discharge_power = device.get("discharge", 0)
            total_power += charge_power - discharge_power
        return round(total_power, 2)

    @property
    def extra_state_attributes(self):
        return {
            "device_count": len(self.coordinator.data),
        }
