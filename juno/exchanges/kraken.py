from __future__ import annotations

from typing import Dict

import simplejson as json

from juno import Fees
from juno.http import ClientSession
from juno.typing import ExcType, ExcValue, Traceback

from .exchange import Exchange

_BASE_URL = 'https://api.kraken.com'


class Kraken(Exchange):
    def __init__(self, api_key: str, secret_key: str) -> None:
        super().__init__()
        self._api_key = api_key
        self._secret_key_bytes = secret_key.encode('utf-8')

    async def __aenter__(self) -> Kraken:
        self._session = ClientSession(raise_for_status=True)
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type: ExcType, exc: ExcValue, tb: Traceback) -> None:
        await self._session.__aexit__(exc_type, exc, tb)

    async def map_fees(self) -> Dict[str, Fees]:
        raise NotImplementedError()

    async def _request(self, method: str, url: str):
        async with self._session.request(method=method, url=_BASE_URL + url) as res:
            return await res.json(loads=json.loads)
