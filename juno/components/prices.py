import asyncio
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from juno.asyncio import enumerate_async
from juno.components import Chandler
from juno.math import floor_multiple
from juno.time import DAY_MS, strftimestamp
from juno.utils import unpack_symbol


class Prices:
    def __init__(self, chandler: Chandler) -> None:
        self._chandler = chandler

    # In the returned prices, the first price is always the opening price of the first candle.
    # When matching with end of period results, don't forget to offset price index by one.
    async def map_asset_prices(
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
            quote_asset, _fiat_asset = unpack_symbol(symbol)
            assert quote_asset not in result
            quote_prices: List[Decimal] = []
            async for candle in self._chandler.stream_candles(
                fiat_exchange, symbol, interval, start, end, fill_missing_with_last=True
            ):
                if len(quote_prices) == 0:
                    quote_prices.append(candle.open)
                quote_prices.append(candle.close)
            result[quote_asset] = quote_prices
        await asyncio.gather(*(assign(s) for s in quote_fiat_symbols))

        # Base -> fiat.
        base_quote_symbols = [s for s in set(symbols) if unpack_symbol(s)[0] not in result]

        # Validate we have enough data.
        await asyncio.gather(
            *(self._validate_start(exchange, s, interval, start) for s in base_quote_symbols),
        )

        # Gather prices.
        async def assign_with_prices(symbol: str) -> None:
            base_asset, quote_asset = unpack_symbol(symbol)
            assert base_asset not in result
            base_prices: List[Decimal] = []
            quote_prices = result[quote_asset]
            async for price_i, candle in enumerate_async(self._chandler.stream_candles(
                exchange, symbol, interval, start, end, fill_missing_with_last=True
            ), 1):
                if len(base_prices) == 0:
                    base_prices.append(
                        candle.open
                        * (quote_prices[0] if quote_asset != fiat_asset else Decimal('1.0'))
                    )
                base_prices.append(
                    candle.close
                    * (quote_prices[price_i] if quote_asset != fiat_asset else Decimal('1.0'))
                )
            result[base_asset] = base_prices
        await asyncio.gather(*(assign_with_prices(s) for s in base_quote_symbols))

        # Add fiat currency itself to prices if it's specified as a quote of any symbol.
        if fiat_asset in (q for _, q in map(unpack_symbol, symbols)):
            result[fiat_asset] = [Decimal('1.0')] * (((end - start) // interval) + 1)

        # # Validate we have enough data points.
        # num_points = (end - start) // interval
        # for asset, prices in result.items():
        #     if len(prices) != num_points:
        #         raise ValueError(
        #             f'Expected {num_points} price points for {asset} but got {len(prices)}'
        #         )

        return result

    async def _validate_start(self, exchange: str, symbol: str, interval: int, start: int) -> None:
        first = await self._chandler.get_first_candle(exchange, symbol, interval)
        if first.time > start:
            raise ValueError(
                f'Unable to map prices; first candle for {symbol} at {strftimestamp(first.time)} '
                f'but requested start at {strftimestamp(start)}'
            )
