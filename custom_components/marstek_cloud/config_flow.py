"""Configuration flow for Marstek Cloud integration.

Security Note:
    Passwords are stored in Home Assistant's config entry data for token refresh.
    Home Assistant encrypts config entries at rest. The password is required in
    plaintext because the Marstek API requires client-side MD5 hashing.
"""

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
            # Security: Password stored in config entry data (encrypted at rest by HA)
            # Required in plaintext because Marstek API needs client-side MD5 hashing
            return self.async_create_entry(
                title="Marstek Cloud",
                data={
                    "email": user_input["email"],
                    "password": user_input["password"],  # Stored securely by HA
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
            # Update config entry data with any changes to email, password, or scan_interval
            new_data = {**self._config_entry.data}
            
            # Handle credentials and scan_interval (stored in data)
            if "email" in user_input:
                new_data["email"] = user_input["email"]
            if "password" in user_input:
                new_data["password"] = user_input["password"]
            if "scan_interval" in user_input:
                new_data["scan_interval"] = user_input["scan_interval"]
            
            # Update the config entry data if there were changes
            if new_data != self._config_entry.data:
                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data
                )
            
            # Remove data fields from user_input, keep only options
            for key in ["email", "password", "scan_interval"]:
                user_input.pop(key, None)
            
            # Save remaining options (device capacities)
            return self.async_create_entry(title="", data=user_input)

        # Generate a schema for editing options
        options = self._config_entry.options
        data = self._config_entry.data
        data_schema = {}
        
        # Add email field
        current_email = data.get("email", "")
        data_schema[
            vol.Optional(
                "email",
                default=current_email,
                description={
                    "suggested_value": current_email,
                    "description": "Marstek cloud account email address",
                },
            )
        ] = str
        
        # Add password field
        current_password = data.get("password", "")
        data_schema[
            vol.Optional(
                "password",
                default=current_password,
                description={
                    "suggested_value": current_password,
                    "description": "Marstek cloud account password",
                },
            )
        ] = str
        
        # Add scan_interval option
        current_scan_interval = options.get("scan_interval", data.get("scan_interval", DEFAULT_SCAN_INTERVAL))
        data_schema[
            vol.Optional(
                "scan_interval",
                default=current_scan_interval,
                description={
                    "suggested_value": current_scan_interval,
                    "description": "Update interval for fetching data from Marstek Cloud API (10-3600 seconds)",
                },
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=10, max=3600))
        
        # Handle missing devices key gracefully
        devices = data.get("devices", [])
        if not devices:
            return self.async_abort(reason="no_devices_found")

        for device in devices:
            devid = device["devid"]
            name = device["name"]
            # Get current capacity from options or device data or default
            current_capacity = options.get(
                f"{devid}_capacity_kwh",
                device.get("capacity_kwh", DEFAULT_CAPACITY_KWH)
            )
            description = f"Set the capacity (in kWh) for {name}"  # Add description for each option
            data_schema[
                vol.Optional(
                    f"{devid}_capacity_kwh",
                    default=current_capacity,
                    description={
                        "suggested_value": current_capacity,
                        "description": description,
                    },
                )
            ] = vol.Coerce(float)

        return self.async_show_form(step_id="init", data_schema=vol.Schema(data_schema))
