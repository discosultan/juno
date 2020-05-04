import asyncio
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from juno.asyncio import resolved_stream, zip_async
from juno.components import Chandler, Historian
from juno.exchanges import Exchange
from juno.math import floor_multiple
from juno.time import DAY_MS, strftimestamp


class Prices:
    def __init__(
        self, chandler: Chandler, historian: Historian, exchanges: List[Exchange]
    ) -> None:
        self._chandler = chandler
        self._historian = historian
        self._exchanges = exchanges

    async def map_prices(
        self,
        exchange: str,
        assets: Iterable[str],
        start: int,
        end: int,
        fiat_exchange: Optional[str] = None,
        fiat_asset: str = 'usdt',
        interval: int = DAY_MS,
    ) -> Dict[str, List[Decimal]]:
        start = floor_multiple(start, interval)
        end = floor_multiple(end, interval)

        fiat_exchange = fiat_exchange or exchange

        # Validate we have enough price data.
        await asyncio.gather(
            self._validate_start(fiat_exchange, f'btc-{fiat_asset}', interval, start),
            *(self._validate_start(
                exchange, f'{a}-btc', interval, start
            ) for a in assets if a != 'btc'),
        )

        result: Dict[str, List[Decimal]] = {}
        quote_fiat_prices = [c.close async for c in self._chandler.stream_candles(
            fiat_exchange, f'btc-{fiat_asset}', interval, start, end, fill_missing_with_last=True
        )]
        result['btc'] = quote_fiat_prices

        async def assign(asset: str) -> None:
            result[asset] = [c.close * p async for c, p in zip_async(
                self._chandler.stream_candles(
                    exchange, f'{asset}-btc', interval, start, end,
                    fill_missing_with_last=True
                ),
                resolved_stream(*quote_fiat_prices)
            )]
        await asyncio.gather(*(assign(a) for a in assets if a != 'btc'))

        return result

    async def _validate_start(self, exchange: str, symbol: str, interval: int, start: int) -> None:
        first = await self._historian.find_first_candle(exchange, symbol, interval)
        if first.time > start:
            raise ValueError(
                f'Unable to map prices; first candle for {symbol} at {strftimestamp(first.time)} '
                f'but requested start at {strftimestamp(start)}'
            )
