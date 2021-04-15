from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncIterable, AsyncIterator

from juno.exchanges.coinbase import Session
from juno.orderbook import Depth
from juno.orderbook.exchanges import Exchange


class Coinbase(Exchange):
    # Capabilities.
    can_stream_depth_snapshot: bool = True

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_depth(self, symbol: str) -> Depth.Snapshot:
        raise ValueError('Not supported')

    @asynccontextmanager
    async def connect_stream_depth(
        self, symbol: str
    ) -> AsyncIterator[AsyncIterable[Depth.Any]]:
        async def inner(
            ws: AsyncIterable[Any]
        ) -> AsyncIterable[Depth.Any]:
            async for data in ws:
                if data['type'] == 'snapshot':
                    yield Depth.Snapshot(
                        bids=[(Decimal(p), Decimal(s)) for p, s in data['bids']],
                        asks=[(Decimal(p), Decimal(s)) for p, s in data['asks']]
                    )
                elif data['type'] == 'l2update':
                    bids = ((p, s) for side, p, s in data['changes'] if side == 'buy')
                    asks = ((p, s) for side, p, s in data['changes'] if side == 'sell')
                    yield Depth.Update(
                        bids=[(Decimal(p), Decimal(s)) for p, s in bids],
                        asks=[(Decimal(p), Decimal(s)) for p, s in asks]
                    )

        async with self._ws.subscribe('level2', ['snapshot', 'l2update'], [symbol]) as ws:
            yield inner(ws)
