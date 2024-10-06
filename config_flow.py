from homeassistant import config_entries
import voluptuous as vol
from homeassistant.core import callback

from . import DOMAIN


class PlayniteMQTTConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Playnite Web MQTT."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            # Validate user input here if needed
            return self.async_create_entry(title="Playnite Web MQTT", data=user_input)

        data_schema = vol.Schema({
            vol.Required("mqtt_broker"): str,
            vol.Required("mqtt_port", default=1883): int,
            vol.Optional("mqtt_username"): str,
            vol.Optional("mqtt_password"): str,
            vol.Optional(
                "topic_base",
                default="playnite/playniteweb_<your-pc-name>",
            ): str,
        })

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PlayniteMQTTOptionsFlow(config_entry)


class PlayniteMQTTOptionsFlow(config_entries.OptionsFlow):
    """Handle an options flow for Playnite Web MQTT."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data_schema = vol.Schema({
            vol.Required(
                "mqtt_broker",
                default=self.config_entry.options.get("mqtt_broker", ""),
            ): str,
            vol.Optional(
                "mqtt_username",
                default=self.config_entry.options.get("mqtt_username", ""),
            ): str,
            vol.Optional(
                "mqtt_password",
                default=self.config_entry.options.get("mqtt_password", ""),
            ): str,
            vol.Optional(
                "topic_base",
                default=self.config_entry.options.get("topic_base", "playnite"),
            ): str,
        })

        return self.async_show_form(step_id="init", data_schema=data_schema)
