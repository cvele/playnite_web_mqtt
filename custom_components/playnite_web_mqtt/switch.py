import asyncio
import base64
import json
import logging
from collections import defaultdict

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import DOMAIN, MAX_CONCURRENT_COMPRESSIONS, STORAGE_VERSION
from .script_executor import ScriptExecutor

compression_semaphore = asyncio.Semaphore(MAX_CONCURRENT_COMPRESSIONS)
COVER_IMAGE_QUEUE: defaultdict[str, list[str]] = defaultdict(list)
_LOGGER = logging.getLogger(__name__)


async def async_added_to_hass(self):
    """Run when the entity is added to Home Assistant."""
    await super().async_added_to_hass()
    _LOGGER.info("Entity %s has been added to Home Assistant", self._name)
    self._async_update_state()


async def async_setup_entry(
    hass: HomeAssistant, config_entry, async_add_entities
):
    """Set up Playnite switches from a config entry."""
    mqtt_handler = hass.data[DOMAIN][config_entry.entry_id]["mqtt_handler"]

    async def on_game_state_update(msg):
        await handle_game_state_update(hass, msg, config_entry)

    await mqtt_handler.subscribe_to_game_state(on_game_state_update)

    await setup_mqtt_subscription(
        hass,
        mqtt_handler,
        handle_mqtt_message,
        config_entry,
        async_add_entities,
    )


async def setup_mqtt_subscription(
    hass: HomeAssistant,
    mqtt_handler,
    callback,
    config_entry,
    async_add_entities,
):
    """Set up the MQTT subscription for both game discovery and covers."""

    def callback_wrapper(msg):
        hass.loop.call_soon_threadsafe(
            hass.async_create_task,
            callback(hass, msg, config_entry, async_add_entities),
        )

    await mqtt_handler.subscribe_to_game_updates(callback_wrapper)


async def handle_game_state_update(hass: HomeAssistant, msg, config_entry):
    """Handle incoming game state updates from the single subscription."""
    try:
        payload = json.loads(msg.payload)
        game_id = payload.get("id")
        game_state = payload.get("state")

        if not game_id:
            _LOGGER.error("Game state update missing game ID: %s", payload)
            return

        if not (
            switch := hass.data[DOMAIN][config_entry.entry_id]["switches"].get(
                game_id
            )
        ):
            _LOGGER.warning("No switch found for game ID %s", game_id)
            return

        _LOGGER.info("Updating state for game %s to %s", game_id, game_state)
        switch.hass = hass
        switch.update_state(game_state)

    except json.JSONDecodeError as e:
        _LOGGER.error(
            "Failed to decode game state message: %s. Message: %s",
            e,
            msg.payload,
        )
    except KeyError as e:
        _LOGGER.error("KeyError when accessing game state data: %s", e)


async def handle_mqtt_message(
    hass: HomeAssistant, msg, config_entry, async_add_entities
):
    """Handle the MQTT message and determine if it's a game or cover."""
    topic = msg.topic
    try:
        if "release" in topic and "cover" in topic:
            await handle_cover_image(hass, msg, config_entry)
        elif "release" in topic:
            await handle_game_discovery(
                hass, msg, config_entry, async_add_entities
            )
        else:
            _LOGGER.warning("Unhandled topic: %s", topic)
    except Exception as e:
        _LOGGER.error("Error handling MQTT message: %s", e)


async def handle_game_discovery(
    hass: HomeAssistant, msg, config_entry, async_add_entities
):
    """Handle the discovery of a game and create a switch for each game."""
    try:
        message = json.loads(msg.payload.decode("utf-8"))
        _LOGGER.info("Game discovery message: %s", message)
    except json.JSONDecodeError:
        _LOGGER.error(
            "Failed to decode game discovery message: %s", msg.payload
        )
        return

    game_id = message.get("id")
    game_name = message.get("name")
    is_installed = message.get("isInstalled")
    if not is_installed:
        _LOGGER.info("Skipping %s, is_installed: %s", game_name, is_installed)
        return

    if not game_id or not game_name:
        _LOGGER.error("Game discovery message missing game ID or name")
        return

    topic_base = config_entry.data.get("topic_base")
    unique_id = f"playnite_game_switch_{game_id}_{topic_base}"

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device({(DOMAIN, topic_base)})

    entity_registry = er.async_get(hass)
    if entity_registry.async_get_entity_id("switch", DOMAIN, unique_id):
        _LOGGER.info(
            "Switch for game %s with ID %s already exists. Skipping creation",
            game_name,
            unique_id,
        )
        return

    switch_data = {"id": game_id, "name": game_name}
    switch = PlayniteGameSwitch(
        switch_data, hass, device, topic_base, config_entry
    )
    hass.data[DOMAIN][config_entry.entry_id]["switches"][game_id] = switch

    async_add_entities([switch])

    if game_id in COVER_IMAGE_QUEUE:
        _LOGGER.info("Processing queued cover images for game %s", game_id)
        for queued_msg in COVER_IMAGE_QUEUE.pop(game_id):
            await switch.handle_cover_image(queued_msg)


async def handle_cover_image(hass: HomeAssistant, msg, config_entry):
    """Handle the cover image received from the MQTT topic."""
    # Extract game ID from the correct position in the topic path
    # Topic format:
    # playnite/playniteweb_<pc>/entity/release/<game-id>/asset/<whatever-here>/type
    topic_parts = msg.topic.split("/")

    if len(topic_parts) >= 6:
        game_id = topic_parts[4]
        if switch := hass.data[DOMAIN][config_entry.entry_id]["switches"].get(
            game_id
        ):
            switch.hass = hass
            await switch.handle_cover_image(msg)
        else:
            _LOGGER.info(
                "No switch found game ID %s to update cover. Queueing",
                game_id,
            )
            COVER_IMAGE_QUEUE[game_id].append(msg)
    else:
        _LOGGER.warning("Unexpected topic format: %s", msg.topic)


class PlayniteGameSwitch(SwitchEntity):
    """Represents a Playnite game switch that controls game state."""

    def __init__(
        self, game_data, hass: HomeAssistant, device, topic_base, config_entry
    ) -> None:
        """Initialize the Playnite game switch."""
        self._name = game_data.get("name")
        self._state = False
        self._game_id = game_data.get("id")
        self._game_data = game_data
        self.device = device
        self.hass = hass
        self.topic_base = topic_base
        self.mqtt_handler = hass.data[DOMAIN][config_entry.entry_id][
            "mqtt_handler"
        ]
        self.config_entry = config_entry
        self._image_data = None
        self._compressed_image_data = None
        self._encoded_image = None
        self.image_compressor = hass.data[DOMAIN][config_entry.entry_id][
            "image_compressor"
        ]
        script_stores = {
            "on_before_start": Store(
                hass,
                STORAGE_VERSION,
                f"{DOMAIN}_{self.config_entry.entry_id}_on_before_start",
            ),
            "on_after_start": Store(
                hass,
                STORAGE_VERSION,
                f"{DOMAIN}_{self.config_entry.entry_id}_on_after_start",
            ),
            "on_before_stop": Store(
                hass,
                STORAGE_VERSION,
                f"{DOMAIN}_{self.config_entry.entry_id}_on_before_stop",
            ),
            "on_after_stop": Store(
                hass,
                STORAGE_VERSION,
                f"{DOMAIN}_{self.config_entry.entry_id}_on_after_stop",
            ),
        }
        self.script_executor = ScriptExecutor(hass, script_stores)

    @callback
    def _async_update_state(self):
        """Update the entity state."""
        if self.hass.is_running:
            self.async_write_ha_state()
        else:
            self.async_schedule_update_ha_state()

    def update_state(self, game_state):
        """Update the switch state based on the game state."""
        self._state = game_state in ["started", "starting"]
        self._async_update_state()

    @property
    def name(self):
        """Return the name of the switch."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique ID of the switch."""
        return f"playnite_game_switch_{self._game_id}"

    @property
    def is_on(self):
        """Return the current state of the switch."""
        return self._state

    def _perform_switch_action(self, action_name, script_before, script_after):
        """Perform the switch action, running scripts before and after."""
        self.script_executor.schedule_script_execution(script_before)
        self._state = action_name == "start"
        self.schedule_update_ha_state()

        if action_name == "start":
            mqtt_action = self.mqtt_handler.send_game_start_request
        else:
            mqtt_action = self.mqtt_handler.send_game_stop_request

        self.hass.loop.call_soon_threadsafe(
            self.hass.async_create_task,
            mqtt_action(self._game_data),
        )

        self.script_executor.schedule_script_execution(script_after)

    def turn_on(self):
        """Turn on the switch (start the game)."""
        self._perform_switch_action(
            "start", "on_before_start", "on_after_start"
        )

    def turn_off(self):
        """Turn off the switch (stop the game)."""
        self._perform_switch_action("stop", "on_before_stop", "on_after_stop")

    @property
    def device_info(self):
        """Return device info for this entity to tie it to the PlayniteWeb."""
        if self.device:
            return {
                "identifiers": self.device.identifiers,
                "manufacturer": self.device.manufacturer,
                "model": self.device.model,
                "name": self.device.name,
                "via_device": self.device.via_device_id,
            }
        _LOGGER.error("Device information is not available")
        return None

    @property
    def entity_picture(self):
        """Return the URL to the entity picture, encoded in base64."""
        if self._image_data and not self._encoded_image:
            self._encoded_image = base64.b64encode(
                self._compressed_image_data
            ).decode("utf-8")
        return (
            f"data:image/jpeg;base64,{self._encoded_image}"
            if self._encoded_image
            else None
        )

    async def handle_cover_image(self, msg):
        """Handle the cover image received from the MQTT topic."""
        try:
            if isinstance(msg.payload, bytes):
                _LOGGER.info(
                    "Received binary cover image for game %s. Size: %d bytes",
                    self._game_id,
                    len(msg.payload),
                )
                self._image_data = msg.payload
                if self._compressed_image_data is None:
                    async with compression_semaphore:
                        self._compressed_image_data = (
                            await self.image_compressor.compress_image(
                                self._image_data
                            )
                        )
                if self.hass and self.hass.loop:
                    self.schedule_update_ha_state()
                else:
                    _LOGGER.error(
                        "Cannot update state, hass is not available for %s",
                        self._name,
                    )
            else:
                _LOGGER.error(
                    "Expected binary payload, but got %s", type(msg.payload)
                )
        except Exception as e:
            _LOGGER.error("Failed to handle cover image: %s", e)
