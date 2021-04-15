import logging
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncIterable, AsyncIterator

from juno.exchanges.binance import Session, to_http_symbol, to_ws_symbol
from juno.orderbook import Depth
from juno.orderbook.exchanges import Exchange
from juno.time import HOUR_SEC

_log = logging.getLogger(__name__)


class Binance(Exchange):
    def __init__(self, session: Session, high_precision: bool = True) -> None:
        self._session = session
        self._high_precision = high_precision

    async def get_depth(self, symbol: str) -> Depth.Snapshot:
        # TODO: We might wanna increase that and accept higher weight.
        LIMIT = 100
        LIMIT_TO_WEIGHT = {
            5: 1,
            10: 1,
            20: 1,
            50: 1,
            100: 1,
            500: 5,
            1000: 10,
            5000: 50,
        }
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#market-data-endpoints
        content = await self._session.request_json(
            'GET',
            '/api/v3/depth',
            weight=LIMIT_TO_WEIGHT[LIMIT],
            data={
                'limit': LIMIT,
                'symbol': to_http_symbol(symbol)
            }
        )
        return Depth.Snapshot(
            bids=[(Decimal(x[0]), Decimal(x[1])) for x in content['bids']],
            asks=[(Decimal(x[0]), Decimal(x[1])) for x in content['asks']],
            last_id=content['lastUpdateId'],
        )

    @asynccontextmanager
    async def connect_stream_depth(self, symbol: str) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Depth.Update]:
            async for data in ws:
                yield Depth.Update(
                    bids=[(Decimal(m[0]), Decimal(m[1])) for m in data['b']],
                    asks=[(Decimal(m[0]), Decimal(m[1])) for m in data['a']],
                    first_id=data['U'],
                    last_id=data['u']
                )

        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/web-socket-streams.md#diff-depth-stream
        url = f'/ws/{to_ws_symbol(symbol)}@depth'
        if self._high_precision:  # Low precision is every 1000ms.
            url += '@100ms'
        async with self._session.connect_refreshing_stream(
            url=url, interval=12 * HOUR_SEC, name='depth', raise_on_disconnect=True
        ) as ws:
            yield inner(ws)
