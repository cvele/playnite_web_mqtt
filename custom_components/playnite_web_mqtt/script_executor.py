import logging
from asyncio import TimeoutError

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

            # Timeout handling and retry mechanism (optional)
            await self._execute_script(script_entity_id)

        except KeyError as ke:
            _LOGGER.error(
                "KeyError while accessing script '%s': %s", script_name, ke
            )
        except TimeoutError as te:
            _LOGGER.error(
                "Timeout while executing script '%s': %s", script_entity_id, te
            )
        except Exception as e:
            _LOGGER.error(
                "Unexpected error while executing script '%s': %s",
                script_name,
                e,
            )

    async def _execute_script(self, script_entity_id, retries=2, timeout=10):
        """Helper method to execute the script with retry and timeout"""
        for attempt in range(1, retries + 1):
            try:
                await self.hass.services.async_call(
                    "script",
                    "turn_on",
                    {"entity_id": script_entity_id},
                    blocking=True,
                    timeout=timeout,
                )
                _LOGGER.info(
                    "Script '%s' executed successfully on attempt %d",
                    script_entity_id,
                    attempt,
                )
                return  # Exit if successful
            except TimeoutError:
                _LOGGER.warning(
                    "Timeout on attempt %d for script '%s'. Retrying...",
                    attempt,
                    script_entity_id,
                )
            except Exception as e:
                _LOGGER.error(
                    "Error on attempt %d for script '%s': %s",
                    attempt,
                    script_entity_id,
                    e,
                )
                if attempt == retries:
                    _LOGGER.error(
                        "Failed to execute script '%s' after %d attempts",
                        script_entity_id,
                        retries,
                    )
                    raise  # Re-raise after final failure
