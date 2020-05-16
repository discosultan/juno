import asyncio
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from juno.asyncio import repeat_async, resolved_stream, zip_async
from juno.components import Chandler, Historian
from juno.math import floor_multiple
from juno.time import DAY_MS, strftimestamp
from juno.utils import unpack_symbol


class Prices:
    def __init__(self, chandler: Chandler, historian: Historian) -> None:
        self._chandler = chandler
        self._historian = historian

    async def map_prices(
        self,
        exchange: str,
        symbols: Iterable[str],
        start: int,
        end: int,
        fiat_exchange: Optional[str] = None,
        fiat_asset: str = 'usdt',
        interval: int = DAY_MS,
    ) -> Dict[str, List[Decimal]]:
        """Maps all assets found in symbols to their fiat prices."""

        start = floor_multiple(start, interval)
        end = floor_multiple(end, interval)

        fiat_exchange = fiat_exchange or exchange

        # Validate we have enough price data.
        quote_fiat_symbols = {
            f'{q}-{fiat_asset}' if q != fiat_asset else f'{b}-{q}'
            for b, q in map(unpack_symbol, symbols)
        }
        await asyncio.gather(
            *(self._validate_start(fiat_exchange, s, interval, start) for s in quote_fiat_symbols),
        )

        result: Dict[str, List[Decimal]] = {}

        # Gather quote fiat prices.
        async def assign(symbol: str) -> None:
            assert fiat_exchange
            q, _ = unpack_symbol(symbol)
            assert q not in result
            result[q] = [c.close async for c in self._chandler.stream_candles(
                fiat_exchange, symbol, interval, start, end, fill_missing_with_last=True
            )]
        await asyncio.gather(*(assign(s) for s in quote_fiat_symbols))

        # Gather base -> quote fiat prices.
        async def assign_with_prices(symbol: str) -> None:
            b, q = unpack_symbol(symbol)
            assert b not in result
            result[b] = [c.close * p async for c, p in zip_async(
                self._chandler.stream_candles(
                    exchange, symbol, interval, start, end, fill_missing_with_last=True
                ),
                resolved_stream(*(result[q]))
                if q != fiat_asset else repeat_async(Decimal('1.0')),
            )]
        await asyncio.gather(
            *(assign_with_prices(s) for s in set(symbols) if unpack_symbol(s)[0] not in result)
        )

        # Add fiat currency itself to prices if it's specified as a quote of any symbol.
        if fiat_asset in (q for _, q in map(unpack_symbol, symbols)):
            result[fiat_asset] = [Decimal('1.0')] * ((end - start) // interval)

        return result

    async def _validate_start(self, exchange: str, symbol: str, interval: int, start: int) -> None:
        first = await self._historian.find_first_candle(exchange, symbol, interval)
        if first.time > start:
            raise ValueError(
                f'Unable to map prices; first candle for {symbol} at {strftimestamp(first.time)} '
                f'but requested start at {strftimestamp(start)}'
            )
