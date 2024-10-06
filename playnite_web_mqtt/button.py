import logging
from homeassistant.components.button import ButtonEntity
from .mqtt_handler import MqttHandler

_LOGGER = logging.getLogger(__name__)
DOMAIN = "playnite_web_mqtt"


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up PlayniteRequestLibraryButton from a config entry."""
    topic_base = config_entry.data.get("topic_base")

    device = hass.data[DOMAIN][config_entry.entry_id]["device"]
    if device is None:
        _LOGGER.error("No device found for topic base %s", topic_base)
        return

    mqtt_handler = hass.data[DOMAIN][config_entry.entry_id]["mqtt_handler"]
    button = PlayniteRequestLibraryButton(
        hass, topic_base, device, config_entry, mqtt_handler
    )
    async_add_entities([button], True)


class PlayniteRequestLibraryButton(ButtonEntity):
    """Represents a button to request the game library from Playnite."""

    def __init__(
        self, hass, topic_base, device, config_entry, mqtt_handler: MqttHandler
    ):
        """Initialize the button entity."""
        self.hass = hass
        self._topic_base = topic_base
        self.device = device
        self.config_entry = config_entry
        self.mqtt_handler = mqtt_handler

    @property
    def name(self):
        """Return the name of the button."""
        return "Request Game Library"

    @property
    def unique_id(self):
        """Return a unique ID for the button."""
        return f"{self._topic_base}_request_library_button"

    @property
    def device_info(self):
        """Device info this entity to tie it to the PlayniteWeb instance."""
        if not self.device:
            _LOGGER.error("Device information is not available.")
            return None

        return {
            "identifiers": self.device.identifiers,
            "manufacturer": self.device.manufacturer,
            "model": self.device.model,
            "name": self.device.name,
            "via_device": self.device.via_device_id,
        }

    async def async_press(self):
        """Handle the button press."""
        _LOGGER.info("Requesting Playnite game library...")
        try:
            await self.mqtt_handler.send_library_request()
        except Exception as e:
            _LOGGER.error("Failed to send library request: %s", e)
