import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.components.mqtt import async_subscribe
from .lib import make_human_friendly
from .mqtt_handler import MqttHandler

_LOGGER = logging.getLogger(__name__)
DOMAIN = "playnite_web_mqtt"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Playnite Web MQTT from a config entry."""
    topic_base = entry.data.get("topic_base")

    if not topic_base:
        _LOGGER.error("No topic base provided in the config entry. Setup failed.")
        return False

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, topic_base)},
        name=make_human_friendly(topic_base),
        manufacturer="Playnite Web",
        model="Playnite Web MQTT",
    )

    # Initialize the MQTT handler and store it along with the entry_id in hass.data
    mqtt_handler = MqttHandler(hass, topic_base)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "device_id": device.id,
        "mqtt_handler": mqtt_handler,
        "switches": {}  # Add a dictionary to store switches by game_id
    }

    # Forward the setup for switch and button platforms
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setups(entry, ["switch", "button"])
    )

    if hass.is_running:
        _LOGGER.info("Home Assistant is already running, sending library request immediately.")
        await mqtt_handler.send_library_request()  # Directly await if Home Assistant is running
    else:
        _LOGGER.info("Home Assistant not fully started, scheduling library request for when ready.")
        # Ensure the task is called in the correct thread using `hass.loop.call_soon_threadsafe`
        def schedule_library_request():
            hass.loop.call_soon_threadsafe(
                hass.async_create_task, mqtt_handler.send_library_request()
            )

        hass.bus.async_listen_once("homeassistant_started", lambda _: schedule_library_request())

    # Subscribe to Playnite connection status
    connection_topic = f"{topic_base}/connection"
    await async_subscribe(hass, connection_topic, lambda msg: hass.async_create_task(handle_playnite_connection(hass, msg, entry.entry_id)))

    return True

async def handle_playnite_connection(hass: HomeAssistant, msg, entry_id):
    """Handle Playnite connection status and trigger library request if online."""
    try:
        connection_status = msg.payload.decode('utf-8')
        _LOGGER.debug(f"Received Playnite connection status: {connection_status}")

        if connection_status == "online":
            mqtt_handler = hass.data[DOMAIN][entry_id]["mqtt_handler"]
            _LOGGER.info("Playnite is online. Sending library request.")
            await mqtt_handler.send_library_request()

    except Exception as e:
        _LOGGER.error(f"Error handling Playnite connection status: {e}")
