import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.components.mqtt import async_subscribe
from .lib import make_human_friendly
from .mqtt_handler import MqttHandler
from .image_compressor import ImageCompressor

_LOGGER = logging.getLogger(__name__)
DOMAIN = "playnite_web_mqtt"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Playnite Web MQTT from a config entry."""
    topic_base = entry.data.get("topic_base")

    if not topic_base:
        _LOGGER.error("No topic base provided in the config entry.")
        return False

    device = await _create_device(hass, entry, topic_base)
    await _initialize_entry_data(hass, entry, device, topic_base)
    await _forward_entry_setups(hass, entry)
    await _schedule_library_request(
        hass, mqtt_handler=hass.data[DOMAIN][entry.entry_id]["mqtt_handler"]
    )

    connection_topic = f"{topic_base}/connection"
    await async_subscribe(
        hass,
        connection_topic,
        lambda msg: hass.async_create_task(
            handle_playnite_connection(hass, msg, entry.entry_id)
        ),
    )

    return True


async def _create_device(
    hass: HomeAssistant, entry: ConfigEntry, topic_base: str
):
    """Create a device in Home Assistant's device registry."""
    device_registry = dr.async_get(hass)
    return device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, topic_base)},
        name=make_human_friendly(topic_base),
        manufacturer="Playnite Web",
        model="Playnite Web MQTT",
    )


async def _initialize_entry_data(
    hass: HomeAssistant, entry: ConfigEntry, device, topic_base: str
):
    """Initialize data for the config entry."""
    mqtt_handler = MqttHandler(hass, topic_base)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "device": device,
        "mqtt_handler": mqtt_handler,
        "image_compressor": ImageCompressor(),
        "switches": {},
    }


async def _forward_entry_setups(hass: HomeAssistant, entry: ConfigEntry):
    """Forward the config entries to appropriate components."""
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setups(
            entry, ["switch", "button"]
        )
    )


async def _schedule_library_request(
    hass: HomeAssistant, mqtt_handler: MqttHandler
):
    """Schedule the sending of a library request based on HA running state."""
    if hass.is_running:
        _LOGGER.info(
            "HASS is already running, sending library request immediately."
        )
        await mqtt_handler.send_library_request()
    else:
        _LOGGER.info("HASS not fully started, scheduling library request.")

        def schedule_library_request():
            hass.loop.call_soon_threadsafe(
                hass.async_create_task, mqtt_handler.send_library_request()
            )

        hass.bus.async_listen_once(
            "homeassistant_started", lambda _: schedule_library_request()
        )


async def handle_playnite_connection(hass: HomeAssistant, msg, entry_id):
    """Handle Playnite connection status updates."""
    try:
        connection_status = msg.payload.decode("utf-8")
        _LOGGER.debug("Playnite connection status: %s", connection_status)

        if connection_status == "online":
            mqtt_handler = hass.data[DOMAIN][entry_id]["mqtt_handler"]
            _LOGGER.info("Playnite is online. Sending library request.")
            await mqtt_handler.send_library_request()

    except Exception as e:
        _LOGGER.error("Error handling Playnite connection status: %s", e)
