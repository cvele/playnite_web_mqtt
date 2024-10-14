import logging

_LOGGER = logging.getLogger(__name__)


class ScriptExecutor:
    """Class responsible for managing and executing scripts."""

    def __init__(self, hass, script_stores):
        """Initialize the script executor."""
        self.hass = hass
        self.script_stores = script_stores

    def schedule_script_execution(self, script_name):
        """Schedule script execution in a thread-safe manner."""
        self.hass.loop.call_soon_threadsafe(
            self.hass.async_create_task,
            self.run_script(script_name),
        )

    async def run_script(self, script_name):
        """Run the selected script from storage if it exists."""
        store = self.script_stores.get(script_name)
        if not store:
            _LOGGER.error("No store found for script '%s'.", script_name)
            return

        try:
            stored_data = await store.async_load()
            script_entity_id = (
                stored_data.get("current_option") if stored_data else None
            )

            if not script_entity_id:
                _LOGGER.debug(
                    "No script selected for '%s'. Stored data: %s",
                    script_name,
                    stored_data,
                )
                return

            _LOGGER.info("Executing script: %s", script_entity_id)

            await self._execute_script(script_entity_id)

        except KeyError as ke:
            _LOGGER.error(
                "KeyError while accessing script '%s': %s", script_name, ke
            )
        except Exception as e:
            _LOGGER.error(
                "Unexpected error while executing script '%s': %s",
                script_name,
                e,
            )

    async def _execute_script(self, script_entity_id):
        """Helper method to execute the script."""
        try:
            await self.hass.services.async_call(
                "script",
                "turn_on",
                {"entity_id": script_entity_id},
                blocking=True,
            )
            _LOGGER.info(
                "Script '%s' executed successfully",
                script_entity_id,
            )
        except Exception as e:
            _LOGGER.error(
                "Error while executing script '%s': %s",
                script_entity_id,
                e,
            )
            raise
