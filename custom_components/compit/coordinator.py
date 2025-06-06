from typing import Any, List
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.core import Config, HomeAssistant
import logging
from datetime import timedelta
import aiohttp
import json

from .types.SystemInfo import Gate
from .types.DeviceDefinitions import DeviceDefinitions
from .types.DeviceState import DeviceInstance, DeviceState
from .api import CompitAPI, CompitFullAPI
from .const import DOMAIN

SCAN_INTERVAL = timedelta(minutes=1)
_LOGGER: logging.Logger = logging.getLogger(__package__)


class CompitDataUpdateCoordinatorPush(DataUpdateCoordinator[dict[Any, DeviceInstance]]):
    """Class to manage fetching data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        gates: List[Gate],
        api: CompitFullAPI,
        device_definitions: DeviceDefinitions,
    ) -> None:
        """Initialize."""
        self.devices: dict[Any, DeviceInstance] = {}
        self.api = api
        self.platforms = []
        self.gates = gates
        self.device_definitions = device_definitions
        self._hass = hass
        self._running = False

        super().__init__(hass, _LOGGER, name=DOMAIN)

    async def _async_update_data(self):
        _LOGGER.info("CompitDataUpdateCoordinatorPush starting...")

        try:
            await self.api.connect_websocket()
            self.api.ws.send_str(f'["4","4","gates:{self.gates[0].id}","phx_join",{{}}]')
            self.api.ws.send_str(f'["7","7","devices:{self.gates[0].devices[0].id}","phx_join",{{}}]')

            self._hass.async_create_task(self._listen_for_messages())
        except Exception as e:
            _LOGGER.error(f"An unexpected error occurred during websocket listening: {e}")
            # TODO
            # self._schedule_reconnect()
        finally:
            _LOGGER.info("Websocket listener stopped.")
            self._websocket = None  # Clear websocket reference
            # Schedule reconnect only if the connection dropped unexpectedly,
            # and there's a valid URL to reconnect to.
            # TODO
            # if self._websocket_url:
            #     self._schedule_reconnect()

    async def _listen_for_messages(self):
        try:
            while not self.api.ws.closed:
                _LOGGER.info("CompitDataUpdateCoordinatorPush listening...")
                message = await self.api.ws.receive()
                if message.type == aiohttp.WSMsgType.TEXT:
                    await self._on_message(message.data)
                elif message.type == aiohttp.WSMsgType.ERROR:
                    _LOGGER.error(f"Websocket error: {message.data}")
                    break  # Break to attempt reconnection
                elif message.type == aiohttp.WSMsgType.CLOSED:
                    _LOGGER.info("Websocket connection closed by server.")

        except aiohttp.ClientError as e:
            _LOGGER.error(f"Websocket communication error: {e}")
        except Exception as e:
            _LOGGER.error(f"An unexpected error occurred during websocket listening: {e}")

    async def _on_message(self, data):
        jdata = json.loads(data)
        if jdata[4] in ["state_update", "selected_params_update"]:
            update_data = jdata[5]

            for gate in self.gates:
                if gate.id != update_data.gate_id:
                    continue
                for device in gate.devices:
                    if device.id != update_data.device_id:
                        continue

                    self.devices[device.id] = DeviceInstance(
                        next(
                            filter(
                                lambda item: item._class == device.class_
                                and item.code == device.type,
                                self.device_definitions.devices,
                            ),
                            None,
                        )
                    )

                    print(
                        f"  Urządzenie: {device.label}, ID: {device.id}, Klasa: {device.class_}, Typ: {device.type}"
                    )
                    state = DeviceState.from_json(update_data.get("state"))
                    self.devices[device.id].state = state

            await self.async_set_updated_data(self.devices)


class CompitDataUpdateCoordinator(DataUpdateCoordinator[dict[Any, DeviceInstance]]):
    """Class to manage fetching data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        gates: List[Gate],
        api: CompitAPI,
        device_definitions: DeviceDefinitions,
    ) -> None:
        """Initialize."""
        self.devices: dict[Any, DeviceInstance] = {}
        self.api = api
        self.platforms = []
        self.gates = gates
        self.device_definitions = device_definitions

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)

    async def _async_update_data(self) -> dict[Any, DeviceInstance]:
        """Update data via library."""
        try:
            for gate in self.gates:
                print(f"Bramka: {gate.label}, Kod: {gate.code}")
                for device in gate.devices:
                    if device.id not in self.devices:
                        self.devices[device.id] = DeviceInstance(
                            next(
                                filter(
                                    lambda item: item._class == device.class_
                                    and item.code == device.type,
                                    self.device_definitions.devices,
                                ),
                                None,
                            )
                        )

                    print(
                        f"  Urządzenie: {device.label}, ID: {device.id}, Klasa: {device.class_}, Typ: {device.type}"
                    )
                    state = await self.api.get_state(device.id)
                    self.devices[device.id].state = state

            return self.devices
        except Exception as exception:
            raise UpdateFailed() from exception
