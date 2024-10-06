import logging
import asyncio
from homeassistant.components.mqtt import async_subscribe
from homeassistant.components.mqtt import async_publish

_LOGGER = logging.getLogger(__name__)

class MqttHandler:
    """Handles MQTT operations for game switches."""

    def __init__(self, hass, topic_base):
        """Initialize the MQTT handler for a specific game."""
        self.hass = hass
        self.topic_base = topic_base
        self.releases_and_cover_topic = f"{self.topic_base}/entity/release/#"  # Wildcard to handle both game releases and covers
        self.state_topic = f"{self.topic_base}/response/game/state"
        self._unsubscribe_callback = None

    async def subscribe_to_game_state(self, callback):
        """Subscribe to the MQTT topic for game state updates."""
        try:
            _LOGGER.debug(f"Subscribing to {self.state_topic}")
            self._unsubscribe_callback = await async_subscribe(self.hass, self.state_topic, callback)
        except Exception as e:
            _LOGGER.error(f"Failed to subscribe to game state: {e}")

    async def subscribe_to_game_updates(self, callback):
        """Subscribe to the MQTT topic for game releases and cover images."""
        try:
            _LOGGER.debug(f"Subscribing to {self.releases_and_cover_topic} for game updates (discovery and cover)")
            self._unsubscribe_callback = await async_subscribe(self.hass, self.releases_and_cover_topic, callback, encoding=None)
        except Exception as e:
            _LOGGER.error(f"Failed to subscribe to game updates: {e}")

    async def unsubscribe(self):
        """Unsubscribe from all MQTT topics."""
        if self._unsubscribe_callback:
            try:
                self._unsubscribe_callback()
                _LOGGER.debug(f"Unsubscribed from game topics")
            except Exception as e:
                _LOGGER.error(f"Failed to unsubscribe from game topics: {e}")

    async def send_game_start_request(self, game_data):
        """Send an MQTT message to start the game."""
        topic = f"playnite/request/game/start"
        await self._publish_mqtt_message(topic, game_data.get('id'))

    async def send_game_stop_request(self, game_data):
        """Send an MQTT message to stop the game."""
        topic = f"playnite/request/game/stop"
        await self._publish_mqtt_message(topic, game_data.get('id'))

    async def send_game_install_request(self, game_data):
        """Send an MQTT message to install the game."""
        topic = f"playnite/request/game/install"
        await self._publish_mqtt_message(topic, game_data.get('id'))

    async def send_game_uninstall_request(self, game_data):
        """Send an MQTT message to uninstall the game."""
        topic = f"playnite/request/game/uninstall"
        await self._publish_mqtt_message(topic, game_data.get('id'))

    async def send_library_request(self):
        """Send an MQTT message to request the game library. No payload needed."""
        topic = f"playnite/request/library"
        await self._publish_mqtt_message(topic)

    async def _publish_mqtt_message(self, topic, payload=None):
        """Publish the MQTT message with retry on failure."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if payload is None:
                    payload = ''
                _LOGGER.debug(f"Publishing to {topic} with payload: {payload}")
                await async_publish(self.hass, topic, payload)
                return
            except Exception as e:
                _LOGGER.error(f"Failed to publish message to {topic} on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)
