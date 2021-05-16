from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Any, AsyncIterable, AsyncIterator

from juno.exchanges.kraken import Kraken as Session
from juno.exchanges.kraken import (
    from_http_timestamp,
    from_ws_timestamp,
    to_http_symbol,
    to_http_timestamp,
    to_ws_symbol,
)
from juno.trades.models import Trade

from .exchange import Exchange


class Kraken(Exchange):
    def __init__(self, session: Session) -> None:
        self._session = session

    async def stream_historical_trades(
        self, symbol: str, start: int, end: int
    ) -> AsyncIterable[Trade]:
        # https://www.kraken.com/en-us/features/api#get-recent-trades
        since = to_http_timestamp(start) - 1  # Exclusive.
        while True:
            res = await self._session.request_public(
                'GET',
                '/0/public/Trades',
                {
                    'pair': to_http_symbol(symbol),
                    'since': since
                },
                cost=2,
            )
            result = res['result']
            last = result['last']

            if last == since:  # No more trades returned.
                break

            since = last
            _, trades = next(iter(result.items()))
            for trade in trades:
                time = from_http_timestamp(trade[2])
                if time >= end:
                    return
                yield Trade(
                    time=time,
                    price=Decimal(trade[0]),
                    size=Decimal(trade[1]),
                )

    @asynccontextmanager
    async def connect_stream_trades(self, symbol: str) -> AsyncIterator[AsyncIterable[Trade]]:
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[Trade]:
            async for trades in ws:
                for trade in trades:
                    yield Trade(
                        time=from_ws_timestamp(trade[2]),
                        price=Decimal(trade[0]),
                        size=Decimal(trade[1]),
                    )

        async with self._session.public_ws.subscribe(
            {'name': 'trade'}, [to_ws_symbol(symbol)]
        ) as ws:
            yield inner(ws)
