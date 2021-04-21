from contextlib import asynccontextmanager
from decimal import Decimal
from time import time
from typing import Any, AsyncIterable, AsyncIterator

import juno.json as json
from juno.exchanges.gateio import Session, to_symbol
from juno.orderbook import Depth
from juno.orderbook.exchanges import Exchange


class GateIO(Exchange):
    def __init__(self, session: Session, high_precision: bool = True) -> None:
        self._session = session
        self._high_precision = high_precision

    async def get_depth(self, symbol: str) -> Depth.Snapshot:
        # https://www.gate.io/docs/apiv4/en/index.html#retrieve-order-book
        content = await self._session.request_json(
            'GET',
            '/api/v4/spot/order_book',
            params={'currency_pair': to_symbol(symbol)},
        )
        return Depth.Snapshot(
            asks=[(Decimal(price), Decimal(size)) for price, size in content['asks']],
            bids=[(Decimal(price), Decimal(size)) for price, size in content['bids']],
        )

    @asynccontextmanager
    async def connect_stream_depth(
        self, symbol: str
    ) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        channel = 'spot.order_book_update'

        # https://www.gateio.pro/docs/apiv4/ws/index.html#changed-order-book-levels
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Depth.Update]:
            async for msg in ws:
                data = json.loads(msg.data)

                if data['channel'] != channel or data['event'] != 'update':
                    continue

                data = data['result']
                yield Depth.Update(
                    bids=[(Decimal(price), Decimal(size)) for price, size in data['b']],
                    asks=[(Decimal(price), Decimal(size)) for price, size in data['a']],
                    first_id=data['U'],
                    last_id=data['u'],
                )

        # TODO: unsubscribe
        async with self._session.ws_connect(_WS_URL) as ws:
            await ws.send_json({
                'time': int(time()),
                'channel': channel,
                'event': 'subscribe',  # 'unsubscribe' for unsubscription
                'payload': [to_symbol(symbol), '100ms' if self._high_precision else '1000ms'],
            })
            yield inner(ws)
