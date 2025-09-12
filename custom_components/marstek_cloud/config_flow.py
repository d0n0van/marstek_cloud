import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN, DEFAULT_SCAN_INTERVAL

DATA_SCHEMA = vol.Schema({
    vol.Required("email"): str,
    vol.Required("password"): str,
    vol.Required(
        "scan_interval",
        default=DEFAULT_SCAN_INTERVAL
    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600))
})

class MarstekConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="Marstek Battery",
                data={
                    "email": user_input["email"],
                    "password": user_input["password"],
                    "scan_interval": user_input["scan_interval"]
                }
            )
        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return MarstekOptionsFlow(config_entry)


class MarstekOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            "scan_interval",
            self.config_entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(
                    "scan_interval",
                    default=current_interval
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600))
            })
        )
