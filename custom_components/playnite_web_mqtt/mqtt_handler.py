import asyncio
import logging

from homeassistant.components.mqtt import async_publish, async_subscribe

_LOGGER = logging.getLogger(__name__)


class MqttHandler:
    """Handles MQTT operations for game switches."""

    def __init__(self, hass, topic_base):
        """Initialize the MQTT handler for a specific game."""
        self.hass = hass
        self.topic_base = topic_base
        self.releases_and_cover_topic = f"{self.topic_base}/entity/release/#"
        self.state_topic = f"{self.topic_base}/response/game/state"
        self._unsubscribe_callback = None
        self.connection_topic = f"{self.topic_base}/connection"

    async def subscribe_to_connection(self, callback, entry_id):
        """Subscribe to the MQTT topic for connection updates."""
        try:
            _LOGGER.debug(
                "Subscribing to %s for connection updates",
                self.connection_topic,
            )

            async def callback_wrapper(msg):
                await callback(self.hass, msg, entry_id)

            self._unsubscribe_callback = await async_subscribe(
                self.hass,
                self.connection_topic,
                callback_wrapper,
            )
        except Exception as e:
            _LOGGER.error("Failed to subscribe to connection topic: %s", e)

    async def subscribe_to_game_state(self, callback):
        """Subscribe to the MQTT topic for game state updates."""
        try:
            _LOGGER.debug("Subscribing to %s", self.state_topic)
            self._unsubscribe_callback = await async_subscribe(
                self.hass, self.state_topic, callback
            )
        except Exception as e:
            _LOGGER.error("Failed to subscribe to game state: %s", e)

    async def subscribe_to_game_updates(self, callback):
        """Subscribe to the MQTT topic for game releases and cover images."""
        try:
            _LOGGER.debug(
                "Subscribing to %s for game updates (discovery and cover)",
                self.releases_and_cover_topic,
            )
            self._unsubscribe_callback = await async_subscribe(
                self.hass,
                self.releases_and_cover_topic,
                callback,
                encoding=None,
            )
        except Exception as e:
            _LOGGER.error("Failed to subscribe to game updates: %s", e)

    async def unsubscribe(self):
        """Unsubscribe from all MQTT topics."""
        if self._unsubscribe_callback:
            try:
                self._unsubscribe_callback()
                _LOGGER.debug("Unsubscribed from game topics")
            except Exception as e:
                _LOGGER.error("Failed to unsubscribe from game topics: %s", e)

    async def send_game_start_request(self, game_data):
        """Send an MQTT message to start the game."""
        topic = "playnite/request/game/start"
        await self._publish_mqtt_message(topic, game_data.get("id"))

    async def send_game_stop_request(self, game_data):
        """Send an MQTT message to stop the game."""
        topic = "playnite/request/game/stop"
        await self._publish_mqtt_message(topic, game_data.get("id"))

    async def send_game_install_request(self, game_data):
        """Send an MQTT message to install the game."""
        topic = "playnite/request/game/install"
        await self._publish_mqtt_message(topic, game_data.get("id"))

    async def send_game_uninstall_request(self, game_data):
        """Send an MQTT message to uninstall the game."""
        topic = "playnite/request/game/uninstall"
        await self._publish_mqtt_message(topic, game_data.get("id"))

    async def send_library_request(self):
        """Send an MQTT message to request the game library."""
        topic = "playnite/request/library"
        await self._publish_mqtt_message(topic)

    async def _publish_mqtt_message(self, topic, payload=None):
        """Publish the MQTT message with retry on failure."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if payload is None:
                    payload = ""
                _LOGGER.debug(
                    "Publishing to %s with payload: %s", topic, payload
                )
                await async_publish(self.hass, topic, payload)
                return
            except Exception as e:
                _LOGGER.error(
                    "Failed to publish message to %s on attempt %d: %s",
                    topic,
                    attempt + 1,
                    e,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5)
