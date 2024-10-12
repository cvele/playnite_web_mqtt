import logging

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from .const import DOMAIN, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config_entry, async_add_entities
):
    """Set up PlayniteRequestLibraryButton from a config entry."""
    topic_base = config_entry.data.get("topic_base")

    device = hass.data[DOMAIN][config_entry.entry_id].get("device")
    if device is None:
        _LOGGER.error("No device found for topic base %s", {topic_base})
        return

    entities = [
        GameScriptSelect(
            hass,
            device,
            config_entry,
            "on_before_start",
            "Run Script Before Start",
        ),
        GameScriptSelect(
            hass,
            device,
            config_entry,
            "on_after_start",
            "Run Script After Start",
        ),
        GameScriptSelect(
            hass,
            device,
            config_entry,
            "on_before_stop",
            "Run Script Before Stop",
        ),
        GameScriptSelect(
            hass,
            device,
            config_entry,
            "on_after_stop",
            "Run Script After Stop",
        ),
    ]

    async_add_entities(entities, True)


class GameScriptSelect(SelectEntity):
    """Representation of a select entity for choosing game scripts."""

    def __init__(
        self,
        hass: HomeAssistant,
        device,
        entry,
        script_name: str,
        friendly_name: str,
    ) -> None:
        """Initialize the select entity."""
        self.hass = hass
        self.device = device
        self.entry = entry
        self.script_name = script_name
        self.friendly_name = friendly_name
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{DOMAIN}_{self.entry.entry_id}_{self.script_name}",
        )
        self._current_option = ""
        self._options = self.get_script_options()

    async def async_added_to_hass(self):
        """Restore the previously saved state from storage."""
        stored_data = await self._store.async_load()
        if stored_data:
            self._current_option = stored_data.get("current_option")
            _LOGGER.info(
                "Restored state for %s: %s",
                self.script_name,
                self._current_option,
            )
        else:
            _LOGGER.info("No previous state found for %s", self.script_name)

        self.async_write_ha_state()

    def get_script_options(self) -> list[str]:
        """Dynamically retrieve the available scripts from Home Assistant."""
        scripts = self.hass.states.async_all("script")
        return [entity.entity_id for entity in scripts]

    async def async_select_option(self, option: str) -> None:
        """Handle the selection of a script with validation."""
        scripts = await self.hass.async_add_executor_job(
            self.get_script_options
        )

        if option not in scripts:
            _LOGGER.error(
                "Selected script '%s' does not exist in Home Assistant", option
            )
            raise ValueError(f"Selected script '{option}' does not exist")

        _LOGGER.info("Selected script: %s for %s", option, self.script_name)
        self._current_option = option

        await self._store.async_save({"current_option": self._current_option})
        self.async_write_ha_state()

    @property
    def name(self) -> str:
        """Return the friendly name of the select entity."""
        return self.friendly_name

    @property
    def unique_id(self) -> str:
        """Return a unique ID for the entity."""
        return f"playnite_game_script_select_{self.script_name}"

    @property
    def options(self) -> list[str]:
        """Return the available options for the select entity."""
        return self._options

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        return self._current_option

    @property
    def device_info(self):
        """Return device info for this entity to tie it to the Playnite Web."""
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
    def entity_category(self):
        """Mark as a configuration entity."""
        return EntityCategory.CONFIG
