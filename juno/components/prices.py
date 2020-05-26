import asyncio
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from juno.asyncio import repeat_async, resolved_stream, zip_async
from juno.components import Chandler
from juno.math import floor_multiple
from juno.time import DAY_MS, strftimestamp
from juno.utils import unpack_symbol


class Prices:
    def __init__(self, chandler: Chandler) -> None:
        self._chandler = chandler

    async def map_prices(
        self,
        exchange: str,
        symbols: Iterable[str],
        start: int,
        end: int,
        interval: int = DAY_MS,
        fiat_exchange: Optional[str] = None,
        fiat_asset: str = 'usdt',
    ) -> Dict[str, List[Decimal]]:
        """Maps all assets found in symbols to their fiat prices."""
        start = floor_multiple(start, interval)
        end = floor_multiple(end, interval)

        fiat_exchange = fiat_exchange or exchange

        result: Dict[str, List[Decimal]] = {}

        # Quote -> fiat.
        quote_fiat_symbols = {
            f'{q}-{fiat_asset}' if q != fiat_asset else f'{b}-{q}'
            for b, q in map(unpack_symbol, symbols)
        }

        # Validate we have enough data.
        await asyncio.gather(
            *(self._validate_start(fiat_exchange, s, interval, start) for s in quote_fiat_symbols),
        )

        # Gather prices.
        async def assign(symbol: str) -> None:
            assert fiat_exchange
            q, _ = unpack_symbol(symbol)
            assert q not in result
            result[q] = [c.close async for c in self._chandler.stream_candles(
                fiat_exchange, symbol, interval, start, end, fill_missing_with_last=True
            )]
        await asyncio.gather(*(assign(s) for s in quote_fiat_symbols))

        # Base -> fiat.
        base_quote_symbols = [s for s in set(symbols) if unpack_symbol(s)[0] not in result]

        # Validate we have enough data.
        await asyncio.gather(
            *(self._validate_start(exchange, s, interval, start) for s in base_quote_symbols),
        )

        # Gather prices.
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
        await asyncio.gather(*(assign_with_prices(s) for s in base_quote_symbols))

        # Add fiat currency itself to prices if it's specified as a quote of any symbol.
        if fiat_asset in (q for _, q in map(unpack_symbol, symbols)):
            result[fiat_asset] = [Decimal('1.0')] * ((end - start) // interval)

        # # Validate we have enough data points.
        # num_points = (end - start) // interval
        # for asset, prices in result.items():
        #     if len(prices) != num_points:
        #         raise ValueError(
        #             f'Expected {num_points} price points for {asset} but got {len(prices)}'
        #         )

        return result

    async def _validate_start(self, exchange: str, symbol: str, interval: int, start: int) -> None:
        first = await self._chandler.find_first_candle(exchange, symbol, interval)
        if first.time > start:
            raise ValueError(
                f'Unable to map prices; first candle for {symbol} at {strftimestamp(first.time)} '
                f'but requested start at {strftimestamp(start)}'
            )
