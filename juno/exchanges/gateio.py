from __future__ import annotations

from contextlib import asynccontextmanager
from types import TracebackType
from typing import Any, AsyncIterable, AsyncIterator, Optional

from juno.common import Depth, ExchangeInfo
from juno.http import ClientSession

from .exchange import Exchange

# https://www.gate.io/docs/apiv4/en/index.html#gate-api-v4
_API_URL = 'https://api.gateio.ws/api/v4'
_WS_URL = 'wss://api.gateio.ws/ws/v4'


class GateIO(Exchange):
    def __init__(self) -> None:
        self._session = ClientSession(raise_for_status=True, name=type(self).__name__)

    async def __aenter__(self) -> GateIO:
        await self._session.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self._session.__aexit__(exc_type, exc, tb)

    async def get_exchange_info(self) -> ExchangeInfo:
        content = await self._request_json('GET', '/spot/currency_pairs')
        # return ExchangeInfo(
        #     filters
        # )

    async def get_depth(self, symbol: str) -> Depth.Snapshot:
        raise NotImplementedError()

    @asynccontextmanager
    async def connect_stream_depth(
        self, symbol: str
    ) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        yield  # type: ignore

    async def _request_json(self, method: str, url: str) -> Any:
        async with self._session.request(method=method, url=_API_URL + url) as response:
            result = await response.json()
        return result
