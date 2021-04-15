from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncIterable, AsyncIterator

from juno.exchanges.coinbase import Session, from_timestamp, to_symbol
from juno.trades import Trade
from juno.trades.exchanges import Exchange


class Coinbase(Exchange):
    def __init__(self, session: Session) -> None:
        self._session = session

    async def stream_historical_trades(
        self, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        trades_desc = []
        async for _, content in self._session.paginated_public_request(
            'GET', f'/products/{to_symbol(symbol)}/trades'
        ):
            done = False
            for val in content:
                time = from_timestamp(val['time'])
                if time >= end:
                    continue
                if time < start:
                    done = True
                    break
                trades_desc.append(Trade(
                    time=time,
                    price=Decimal(val['price']),
                    size=Decimal(val['size'])
                ))
            if done:
                break
        for trade in reversed(trades_desc):
            yield trade

    @asynccontextmanager
    async def connect_stream_trades(self, symbol: str) -> AsyncIterator[AsyncIterable[Trade]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Trade]:
            async for val in ws:
                if val['type'] == 'last_match':
                    # TODO: Useful for recovery process that downloads missed trades after a dc.
                    continue
                if 'price' not in val or 'size' not in val:
                    continue
                yield Trade(
                    time=from_timestamp(val['time']),
                    price=Decimal(val['price']),
                    size=Decimal(val['size'])
                )

        async with self._ws.subscribe('matches', ['last_match', 'match'], [symbol]) as ws:
            yield inner(ws)
