import asyncio
from decimal import Decimal
from typing import Iterable, Optional

from asyncstdlib import enumerate as enumerate_async

from juno import Candle
from juno.components import Chandler
from juno.math import floor_multiple
from juno.time import DAY_MS, strftimestamp
from juno.utils import unpack_assets


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
        fiat_asset: str = "usdt",
    ) -> dict[str, list[Decimal]]:
        """Maps all assets found in symbols to their fiat prices."""
        start = floor_multiple(start, interval)
        end = floor_multiple(end, interval)

        fiat_exchange = fiat_exchange or exchange

        result: dict[str, list[Decimal]] = {}

        # Quote -> fiat.
        quote_fiat_symbols = {
            f"{q}-{fiat_asset}" if q != fiat_asset else f"{b}-{q}"
            for b, q in map(unpack_assets, symbols)
        }

        # Validate we have enough data.
        await asyncio.gather(
            *(self._validate_start(fiat_exchange, s, interval, start) for s in quote_fiat_symbols),
        )

        # Gather prices.
        async def assign(symbol: str) -> None:
            assert fiat_exchange
            quote_asset, _fiat_asset = unpack_assets(symbol)
            assert quote_asset not in result
            quote_prices: list[Decimal] = []
            last_candle: Optional[Candle] = None
            async for candle in self._chandler.stream_candles_fill_missing_with_none(
                fiat_exchange, symbol, interval, start, end
            ):
                if len(quote_prices) == 0:
                    if candle is None:
                        raise ValueError("Candle missing from start")
                    quote_prices.append(candle.open)
                price = last_candle.close if candle is None else candle.close  # type: ignore
                quote_prices.append(price)
                if candle:
                    last_candle = candle
            result[quote_asset] = quote_prices

        await asyncio.gather(*(assign(s) for s in quote_fiat_symbols))

        # Base -> fiat.
        base_quote_symbols = [s for s in set(symbols) if unpack_assets(s)[0] not in result]

        # Validate we have enough data.
        await asyncio.gather(
            *(self._validate_start(exchange, s, interval, start) for s in base_quote_symbols),
        )

        # Gather prices.
        async def assign_with_prices(symbol: str) -> None:
            base_asset, quote_asset = unpack_assets(symbol)
            assert base_asset not in result
            base_prices: list[Decimal] = []
            quote_prices = result[quote_asset]
            last_candle: Optional[Candle] = None
            async for price_i, candle in enumerate_async(
                self._chandler.stream_candles_fill_missing_with_none(
                    exchange=exchange,
                    symbol=symbol,
                    interval=interval,
                    start=start,
                    end=end,
                ),
                1,
            ):
                if len(base_prices) == 0:
                    if candle is None:
                        raise ValueError("Candle missing from start")
                    base_prices.append(
                        candle.open
                        * (quote_prices[0] if quote_asset != fiat_asset else Decimal("1.0"))
                    )
                price = last_candle.close if candle is None else candle.close  # type: ignore
                base_prices.append(
                    price
                    * (quote_prices[price_i] if quote_asset != fiat_asset else Decimal("1.0"))
                )
                if candle:
                    last_candle = candle
            result[base_asset] = base_prices

        await asyncio.gather(*(assign_with_prices(s) for s in base_quote_symbols))

        # Add fiat currency itself to prices if it's specified as a quote of any symbol.
        if fiat_asset in (q for _, q in map(unpack_assets, symbols)):
            result[fiat_asset] = [Decimal("1.0")] * (((end - start) // interval) + 1)

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
                f"Unable to map prices; first candle for {symbol} at {strftimestamp(first.time)} "
                f"but requested start at {strftimestamp(start)}"
            )
