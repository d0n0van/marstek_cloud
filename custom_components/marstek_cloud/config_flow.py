import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from .const import DEFAULT_CAPACITY_KWH, DEFAULT_SCAN_INTERVAL, DOMAIN

DATA_SCHEMA = vol.Schema(
    {
        vol.Required("email"): str,
        vol.Required("password"): str,
        vol.Required("scan_interval", default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=10, max=3600)
        ),
        vol.Optional("default_capacity_kwh", default=5.12): vol.All(
            vol.Coerce(float), vol.Range(min=0.1, max=100)
        ),  # Rename capacity_kwh to default_capacity_kwh
    }
)


class MarstekConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="Marstek Cloud",
                data={
                    "email": user_input["email"],
                    "password": user_input["password"],
                    "scan_interval": user_input["scan_interval"],
                    "default_capacity_kwh": user_input.get(
                        "default_capacity_kwh", 5.12
                    ),  # Default capacity in kwh for all devices
                },
            )
        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return MarstekOptionsFlow(config_entry)


class MarstekOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Marstek integration."""

    def __init__(self, config_entry):
        self._config_entry = (
            config_entry  # Use a private attribute to avoid deprecation warnings
        )

    async def async_step_init(self, user_input=None):
        """Manage the options for the integration."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Generate a schema for editing capacity_kwh for each battery with descriptions
        options = self._config_entry.options
        data_schema = {}
        
        # Add scan_interval option
        data_schema[
            vol.Optional(
                "scan_interval",
                default=options.get("scan_interval", self._config_entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL)),
                description={
                    "suggested_value": DEFAULT_SCAN_INTERVAL,
                    "description": "Update interval for fetching data from Marstek Cloud API (10-3600 seconds)",
                },
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=10, max=3600))
        
        # Handle missing devices key gracefully
        devices = self._config_entry.data.get("devices", [])
        if not devices:
            return self.async_abort(reason="no_devices_found")

        for device in devices:
            devid = device["devid"]
            name = device["name"]
            description = f"Set the capacity (in kWh) for {name}"  # Add description for each option
            data_schema[
                vol.Optional(
                    f"{devid}_capacity_kwh",
                    default=options.get(f"{devid}_capacity_kwh", DEFAULT_CAPACITY_KWH),
                    description={
                        "suggested_value": DEFAULT_CAPACITY_KWH,
                        "description": description,
                    },
                )
            ] = vol.Coerce(float)

        return self.async_show_form(step_id="init", data_schema=vol.Schema(data_schema))
