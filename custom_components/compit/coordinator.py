from typing import Any, List
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import Config, HomeAssistant
import logging
from datetime import timedelta, datetime

from .types.SystemInfo import Gate
from .types.DeviceDefinitions import DeviceDefinitions
from .types.DeviceState import DeviceInstance
from .api import CompitAPI
from .const import DOMAIN, PARAMS_GROUPS

SCAN_INTERVAL = timedelta(minutes=1)
RQUEST_SELECTED_PARAMS_INTERVAL = timedelta(minutes=1)
_LOGGER: logging.Logger = logging.getLogger(__package__)

class CompitDataUpdateCoordinator(DataUpdateCoordinator[dict[Any, DeviceInstance]]):
    """Class to manage fetching data from the API."""

    def __init__(self, hass: HomeAssistant, gates: List[Gate], api: CompitAPI, device_definitions: DeviceDefinitions) -> None:
        """Initialize."""
        self.devices: dict[Any, DeviceInstance] = {}
        self.api = api
        self.platforms = []
        self.gates = gates
        self.device_definitions = device_definitions
        self.last_selected_params_time = datetime.now()

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self) -> dict[Any, DeviceInstance] :
        """Update data via library."""
        try:
            for gate in self.gates:
                print(f"Bramka: {gate.label}, Kod: {gate.code}")
                for device in gate.devices:
                    if device.id not in self.devices:
                        self.devices[device.id] = DeviceInstance(next(filter(lambda item: item._class == device.class_ and item.code == device.type, self.device_definitions.devices), None))

                    print(f"  Urządzenie: {device.label}, ID: {device.id}, Klasa: {device.class_}, Typ: {device.type}")
                    # state = await self.api.get_state(device.id)
                    state = await self.api.get_full_state(gate.id, device.id)
                    self.devices[device.id].state = state
                    _LOGGER.warning(state.params)

                    # request selected params refresh
                    if datetime.now() - self.last_selected_params_time >= RQUEST_SELECTED_PARAMS_INTERVAL:
                        self.last_selected_params_time = datetime.now()
                        await self.api.get_selected_params(gate.code, device.id, PARAMS_GROUPS[0])

            return self.devices
        except Exception as exception:
            raise UpdateFailed() from exception