import asyncio
import base64
import json
import logging
from collections import defaultdict
import traceback
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store

from .const import DOMAIN, MAX_CONCURRENT_COMPRESSIONS, STORAGE_VERSION
from .script_executor import ScriptExecutor

compression_semaphore = asyncio.Semaphore(MAX_CONCURRENT_COMPRESSIONS)
COVER_IMAGE_QUEUE: defaultdict[str, list[str]] = defaultdict(list)
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config_entry, async_add_entities
):
    """Set up Playnite switches from a config entry."""
    _LOGGER.debug(
        "async_setup_entry: async_add_entities passed: %s", async_add_entities
    )
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
    mqtt_callback,
    config_entry,
    async_add_entities,
):
    """Set up the MQTT subscription for both game discovery and covers."""

    def callback_wrapper(msg):
        hass.loop.call_soon_threadsafe(
            hass.async_create_task,
            mqtt_callback(hass, msg, config_entry, async_add_entities),
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

        switch = hass.data[DOMAIN][config_entry.entry_id]["switches"].get(
            game_id
        )
        if not switch:
            _LOGGER.warning(
                "No switch found for game ID %s while handling game state "
                "update",
                game_id,
            )
            return

        _LOGGER.info("Updating state for game %s to %s", game_id, game_state)
        switch.update_state(game_state)

    except (json.JSONDecodeError, KeyError) as e:
        _LOGGER.error(
            "Failed to handle game state message: %s. Message: %s",
            e,
            msg.payload,
        )


async def handle_mqtt_message(
    hass: HomeAssistant, msg, config_entry, async_add_entities
):
    """Handle the MQTT message and determine if it's a game or cover."""
    topic = msg.topic
    try:
        if "release" in topic and "cover" in topic:
            _LOGGER.debug("Received cover image for game %s", topic)
            handle_cover_image(hass, msg, config_entry)
        elif "release" in topic:
            _LOGGER.debug("Received game discovery message for %s", topic)
            await handle_game_discovery(
                hass, msg, config_entry, async_add_entities
            )
        else:
            _LOGGER.warning("Unhandled topic: %s", topic)
    except Exception:
        _LOGGER.exception("Error handling MQTT message")
        _LOGGER.debug("Full traceback: %s", traceback.format_exc())


async def handle_game_discovery(
    hass: HomeAssistant, msg, config_entry, async_add_entities
):
    """Handle the discovery of a game and create a switch for each game."""

    _LOGGER.debug(
        "handle_game_discovery: async_add_entities passed: %s",
        async_add_entities,
    )
    try:
        message = json.loads(msg.payload.decode("utf-8"))
    except json.JSONDecodeError:
        _LOGGER.error(
            "Failed to decode game discovery message: %s", msg.payload
        )
        return

    release_id = msg.topic.split("/")[-1]
    game_id = message.get("id")
    game_name = message.get("name")
    is_installed = message.get("isInstalled")
    if not is_installed:
        _LOGGER.info("Skipping %s, is_installed: %s", game_name, is_installed)
        _LOGGER.debug(
            "Clearing cover image queue for game %s since it's not installed",
            game_id,
        )
        COVER_IMAGE_QUEUE.pop(game_id, None)
        return

    if not game_id or not game_name or not release_id:
        _LOGGER.error(
            "Game discovery message missing release ID, game ID or name"
        )
        return

    if release_id in hass.data[DOMAIN][config_entry.entry_id]["switches"]:
        _LOGGER.info(
            "Switch already exists for game release %s (%s)",
            game_name,
            release_id,
        )
        return

    topic_base = config_entry.data.get("topic_base")
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device({(DOMAIN, topic_base)})

    switch_data = {
        "id": game_id,
        "name": game_name,
        "release_id": release_id,
        "is_installed": is_installed,
    }
    switch = PlayniteGameSwitch(
        switch_data, hass, device, topic_base, config_entry
    )
    async_add_entities([switch])


def handle_cover_image(hass: HomeAssistant, msg, config_entry):
    """Handle the cover image received from the MQTT topic."""
    topic_parts = msg.topic.split("/")

    if len(topic_parts) < 6:
        raise ValueError(f"Unexpected topic format: {msg.topic}")

    release_id = topic_parts[4]
    if not release_id:
        raise ValueError(f"No game ID found in topic: {msg.topic}")

    switch = hass.data[DOMAIN][config_entry.entry_id]["switches"].get(
        release_id
    )
    if not switch:
        _LOGGER.info(
            "Switch not found for game release %s, queuing image", release_id
        )
        COVER_IMAGE_QUEUE[release_id].append(msg)
        return

    if switch.is_installed():
        _LOGGER.info(
            "Game is installed. Handling cover image for game release %s",
            release_id,
        )
        hass.loop.call_soon_threadsafe(
            hass.async_create_task,
            switch.handle_cover_image(msg),
        )
    else:
        _LOGGER.info(
            "Game release %s is not installed, clearing queue cover image",
            release_id,
        )
        COVER_IMAGE_QUEUE.pop(release_id, None)


class PlayniteGameSwitch(SwitchEntity):
    """Represents a Playnite game switch that controls game state."""

    def __init__(
        self, game_data, hass: HomeAssistant, device, topic_base, config_entry
    ) -> None:
        """Initialize the Playnite game switch."""
        self._name = game_data.get("name")
        self._state = False
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
        self.original_image_hash = None
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

    async def async_added_to_hass(self):
        """Run when the entity is added to Home Assistant."""
        await super().async_added_to_hass()
        _LOGGER.info("Switch %s has been added to Home Assistant", self._name)
        self.hass.data[DOMAIN][self.config_entry.entry_id]["switches"][
            self.release_id()
        ] = self
        if self.release_id() in COVER_IMAGE_QUEUE:
            _LOGGER.info(
                "Switch added to HASS. Processing queued images, release %s",
                self.release_id(),
            )
            for queued_msg in COVER_IMAGE_QUEUE.pop(self.release_id()):
                await self.handle_cover_image(queued_msg)

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
        base_id = (
            f"pwms_{self.topic_base}_{self.game_id()}_{self.release_id()}"
        )
        return base_id.replace("/", "_")

    @property
    def is_on(self):
        """Return the current state of the switch."""
        return self._state

    def is_installed(self):
        """Return whether the game is installed."""
        return self._validate_game_data(
            "is_installed", "Game installation status is not available"
        )

    def game_id(self):
        """Return the game ID."""
        return self._validate_game_data("id", "Game ID is not available")

    def release_id(self):
        """Return the release ID."""
        return self._validate_game_data(
            "release_id", "Release ID is not available"
        )

    def _validate_game_data(self, arg0, arg1):
        if not self._game_data:
            raise ValueError("Game data is not available")
        if not self._game_data.get(arg0):
            raise ValueError(arg1)
        return self._game_data.get(arg0)

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
        """
        Return device info for this entity to tie it to the PlayniteWeb.
        """
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
                    "Received image for game %s, release %s. Size: %d bytes",
                    self.game_id(),
                    self.release_id(),
                    len(msg.payload),
                )
                self._image_data = msg.payload
                payload_hash = hash(self._image_data)
                if (
                    payload_hash == self.original_image_hash
                    and self._compressed_image_data
                ):
                    _LOGGER.info(
                        "Image data is the same as previous, not compressing"
                    )
                    return

                if self._compressed_image_data is None:
                    async with compression_semaphore:
                        try:
                            self._compressed_image_data = (
                                await self.image_compressor.compress_image(
                                    self._image_data
                                )
                            )
                            self.original_image_hash = payload_hash
                        except Exception as compression_error:
                            _LOGGER.error(
                                "Image compression failed: %s",
                                compression_error,
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
