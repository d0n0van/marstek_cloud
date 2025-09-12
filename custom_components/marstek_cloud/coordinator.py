import hashlib
import aiohttp
import async_timeout
import time
import logging
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import API_LOGIN, API_DEVICES

_LOGGER = logging.getLogger(__name__)

class MarstekAPI:
    def __init__(self, session: aiohttp.ClientSession, email: str, password: str):
        self._session = session
        self._email = email
        self._password = password
        self._token = None

    async def _get_token(self):
        md5_pwd = hashlib.md5(self._password.encode()).hexdigest()
        params = {"pwd": md5_pwd, "mailbox": self._email}
        async with async_timeout.timeout(10):
            async with self._session.post(API_LOGIN, params=params) as resp:
                data = await resp.json()
                if "token" not in data:
                    raise UpdateFailed(f"Login failed: {data}")
                self._token = data["token"]
                _LOGGER.info("Marstek: Obtained new API token")

    async def get_devices(self):
        if not self._token:
            await self._get_token()

        params = {"token": self._token}
        async with async_timeout.timeout(10):
            async with self._session.get(API_DEVICES, params=params) as resp:
                data = await resp.json()

                if str(data.get("code")) in ("-1", "401", "403") or "token" in str(data).lower():
                    _LOGGER.warning("Marstek: Token expired or invalid, refreshing...")
                    await self._get_token()
                    params["token"] = self._token
                    async with self._session.get(API_DEVICES, params=params) as retry_resp:
                        data = await retry_resp.json()

                if "data" not in data:
                    raise UpdateFailed(f"Device fetch failed: {data}")

                return data["data"]

class MarstekCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, api: MarstekAPI, scan_interval: int):
        super().__init__(
            hass,
            logger=_LOGGER,
            name="Marstek Battery",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self.last_latency = None

    async def _async_update_data(self):
        start = time.perf_counter()
        devices = await self.api.get_devices()
        self.last_latency = round((time.perf_counter() - start) * 1000, 1)
        return devices
