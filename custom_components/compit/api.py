import logging
import asyncio
from typing import Any

from .types.DeviceState import DeviceState
from .types.SystemInfo import SystemInfo
from .const import API_URL, FULL_API_URL
import aiohttp
import async_timeout
from bs4 import BeautifulSoup

TIMEOUT = 10
_LOGGER: logging.Logger = logging.getLogger(__package__)
HEADERS = {"Content-type": "application/json; charset=UTF-8"}


class CompitFullAPI:
    def __init__(self, email, password, session: aiohttp.ClientSession):
        self.email = email
        self.password = password
        self.token = None
        self._api_wrapper = ApiWrapper(session)
        self._session = session
        self.ws: aiohttp.WS | None = None

    async def get_result(
        self, response: aiohttp.ClientResponse, ignore_response_code: bool = False
    ) -> Any:
        if response.ok or ignore_response_code:
            return await response.json()

        raise Exception(f"Server returned: {response.status} {response.reason}")

    async def authenticate(self):
        try:
            response1 = await self._api_wrapper.get(f"{FULL_API_URL}/pl/login")
            s = BeautifulSoup(await response1.text(), features="html.parser")
            _csrf_token = s.find('input', {'name': '_csrf_token'}).attrs.get("value")
            response = await self._api_wrapper.post(
                f"{FULL_API_URL}/pl/login",
                {
                    "email": self.email,
                    "password": self.password,
                    "_csrf_token": _csrf_token,
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 OPR/119.0.0.0",
                    "Content-Type": "application/x-www-form-urlencoded"
                },
            )

            if response.status == 200:
                s = BeautifulSoup(await response.text(), features="html.parser")
                self.token = s.find('meta', {'id': 'token'}).attrs.get("content")

                # load system info
                response = await self._api_wrapper.get(f"{FULL_API_URL}/api/current_user", headers={
                    "Authorization": f"Bearer {self.token}"
                })
                result = await self.get_result(response)
                return SystemInfo.from_json(result)
            else:
                raise Exception("Login response code: %s" % response.status)
        except Exception as e:
            _LOGGER.error(e)
            return False

    async def get_wentilation_group_id(self, gate_id: int) -> int:
        try:
            response = await self._api_wrapper.get(f"{FULL_API_URL}/api/gates/{gate_id}/device_definitions/list")
            result = await self.get_result(response)
            for group in result[0].get("params_groups", []):
                if "Wentylacja" in group.get("label"):
                    return group.get("id")
        except Exception as e:
            _LOGGER.error(e)
            return False

    async def request_parameters(self, gate_code: str, device_id: int, group_id: int):
        try:
            response = await self._api_wrapper.post(
                f"{FULL_API_URL}/api/gates/{gate_code}/devices/{device_id}/selected_params",
                data={"group_id": group_id},
            )
            await self.get_result(response)
        except Exception as e:
            _LOGGER.error(e)
            return False

    async def connect_websocket(self):
        websocket_url = f"wss://inext.compit.pl/socket/websocket?token={self.token}&vsn=2.0.0"
        self.ws = await self._session.ws_connect(websocket_url)


class CompitAPI:
    def __init__(self, email, password, session: aiohttp.ClientSession):
        self.email = email
        self.password = password
        self.token = None
        self._api_wrapper = ApiWrapper(session)

    async def authenticate(self):
        try:
            response = await self._api_wrapper.post(
                f"{API_URL}/authorize",
                {
                    "email": self.email,
                    "password": self.password,
                    "uid": "HomeAssistant",
                    "label": "HomeAssistant",
                },
            )

            if response.status == 422:
                result = await self.get_result(response, ignore_response_code=True)
                self.token = result["token"]
                response = await self._api_wrapper.post(
                    f"{API_URL}/clients",
                    {
                        "fcm_token": None,
                        "uid": "HomeAssistant",
                        "label": "HomeAssistant",
                    },
                    auth=self.token,
                )

                result = await self.get_result(response)
                return self.authenticate()

            result = await self.get_result(response)
            self.token = result["token"]
            return SystemInfo.from_json(result)
        except Exception as e:
            _LOGGER.error(e)
            return False

    async def get_gates(self):
        try:
            response = await self._api_wrapper.get(f"{API_URL}/gates", {}, self.token)

            return SystemInfo.from_json(await self.get_result(response))
        except Exception as e:
            _LOGGER.error(e)
            return False

    async def get_state(self, device_id: int):
        try:
            response = await self._api_wrapper.get(
                f"{API_URL}/devices/{device_id}/state", {}, self.token
            )

            return DeviceState.from_json(await self.get_result(response))

        except Exception as e:
            _LOGGER.error(e)
            return False

    async def update_device_parameter(
        self, device_id: int, parameter: str, value: str | int
    ):
        try:
            print(f"Set {parameter} to {value} for device {device_id}")
            _LOGGER.info(f"Set {parameter} to {value} for device {device_id}")

            data = {"values": [{"code": parameter, "value": value}]}

            response = await self._api_wrapper.put(
                f"{API_URL}/devices/{device_id}/params", data=data, auth=self.token
            )
            return await self.get_result(response)

        except Exception as e:
            _LOGGER.error(e)
            return False

    async def get_result(
        self, response: aiohttp.ClientResponse, ignore_response_code: bool = False
    ) -> Any:
        if response.ok or ignore_response_code:
            return await response.json()

        raise Exception(f"Server returned: {response.status} {response.reason}")


class ApiWrapper:
    """Helper class"""

    def __init__(self, session: aiohttp.ClientSession):
        self._session = session

    async def get(
        self, url: str, headers: dict = {}, auth: Any = None
    ) -> aiohttp.ClientResponse:
        """Run http GET method"""
        if auth:
            headers["Authorization"] = auth

        return await self.api_wrapper("get", url, headers=headers, auth=None)

    async def post(
        self, url: str, data: dict = {}, headers: dict = {}, auth: Any = None
    ) -> aiohttp.ClientResponse:
        """Run http POST method"""
        if auth:
            headers["Authorization"] = auth

        return await self.api_wrapper(
            "post", url, data=data, headers=headers, auth=None
        )

    async def put(
        self, url: str, data: dict = {}, headers: dict = {}, auth: Any = None
    ) -> aiohttp.ClientResponse:
        """Run http PUT method"""
        if auth:
            headers["Authorization"] = auth

        return await self.api_wrapper("put", url, data=data, headers=headers, auth=None)

    async def api_wrapper(
        self,
        method: str,
        url: str,
        data: dict = {},
        headers: dict = {},
        auth: Any = None,
    ) -> Any:
        """Get information from the API."""
        try:
            async with async_timeout.timeout(TIMEOUT):
                if method == "get":
                    response = await self._session.get(url, headers=headers, auth=auth)
                    return response

                elif method == "post":
                    response = await self._session.post(
                        url, headers=headers, data=data, auth=auth
                    )
                    return response
                elif method == "put":
                    response = await self._session.put(
                        url, headers=headers, json=data, auth=auth
                    )
                    return response

        except asyncio.TimeoutError as exception:
            _LOGGER.error(
                "Timeout error fetching information from %s - %s",
                url,
                exception,
            )
