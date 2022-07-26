import asyncio
import logging
from decimal import Decimal
from typing import Iterable, Optional

from juno import Asset, Candle, Interval, Interval_, Symbol, Symbol_, Timestamp, Timestamp_
from juno.components import Chandler, Informant
from juno.math import floor_multiple

_log = logging.getLogger(__name__)


class InsufficientPrices(Exception):
    pass


class Prices:
    def __init__(self, informant: Informant, chandler: Chandler) -> None:
        self._informant = informant
        self._chandler = chandler

    # In the returned prices, the first price is always the opening price of the first candle.
    # When matching with end of period results, don't forget to offset price index by one.
    async def map_asset_prices(
        self,
        exchange: str,
        assets: Iterable[Asset],
        start: Timestamp,
        end: Timestamp,
        interval: Interval = Interval_.DAY,
        target_asset: Asset = "usdt",
    ) -> dict[Asset, list[Decimal]]:
        """Creates a mapping of assets to target asset prices."""
        result: dict[str, list[Decimal]] = {}

        start = floor_multiple(start, interval)
        end = floor_multiple(end, interval)
        unique_assets = set(assets)

        _log.info(
            f"mapping {target_asset} prices from {exchange} between "
            f"{Timestamp_.format_span(start, end)} for {unique_assets}"
        )

        supported_symbols = set(self._informant.list_symbols(exchange))

        # We can fetch prices directly for these symbols.
        direct_symbols = [
            symbol
            for a in unique_assets
            if a != target_asset and (symbol := f"{a}-{target_asset}") in supported_symbols
        ]
        _log.info(f"can directly map {direct_symbols}")

        # Validate we have enough data.
        await asyncio.gather(
            *(
                self._validate_sufficient_data(exchange, s, interval, start, end)
                for s in direct_symbols
            ),
        )

        # Gather direct prices.
        async def assign_direct(symbol: Symbol) -> None:
            base_asset = Symbol_.base_asset(symbol)
            assert base_asset not in result
            result[base_asset] = await self._list_prices(exchange, symbol, interval, start, end)

        await asyncio.gather(*(assign_direct(s) for s in direct_symbols))

        # We need to use an intermediary asset to find these prices. Currently we only support BTC
        # for that.
        indirect_assets = [
            a
            for a in unique_assets
            if a != target_asset and f"{a}-{target_asset}" not in supported_symbols
        ]
        if len(indirect_assets) > 0:
            assert target_asset != "btc"

            _log.info(f"have to indirectly map {indirect_assets}")

            btc_prices = await self._list_prices(
                exchange, f"btc-{target_asset}", interval, start, end
            )

            # Gather indirect prices.
            async def assign_indirect(asset: Asset) -> None:
                assert asset not in result
                intermediary_symbol = f"{asset}-btc"
                intermediary_prices = await self._list_prices(
                    exchange, intermediary_symbol, interval, start, end
                )
                result[asset] = [a * b for a, b in zip(intermediary_prices, btc_prices)]

            await asyncio.gather(*(assign_indirect(s) for s in indirect_assets))

        # Add fiat currency itself to prices if it's specified as a quote of any symbol.
        if target_asset in unique_assets:
            result[target_asset] = [Decimal("1.0")] * (((end - start) // interval) + 1)

        return result

    async def _list_prices(
        self,
        exchange: str,
        symbol: Symbol,
        interval: Interval,
        start: Timestamp,
        end: Timestamp,
    ) -> list[Decimal]:
        prices: list[Decimal] = []
        last_candle: Optional[Candle] = None
        async for candle in self._chandler.stream_candles_fill_missing_with_none(
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
        ):
            if len(prices) == 0:
                if candle is None:
                    raise ValueError("Candle missing from start")
                prices.append(candle.open)
            price = last_candle.close if candle is None else candle.close  # type: ignore
            prices.append(price)
            if candle:
                last_candle = candle
        return prices

    async def _validate_sufficient_data(
        self,
        exchange: str,
        symbol: Symbol,
        interval: Interval,
        start: Timestamp,
        end: Timestamp,
    ) -> None:
        first, last = await asyncio.gather(
            self._chandler.get_first_candle(exchange, symbol, interval),
            self._chandler.get_last_candle(exchange, symbol, interval),
        )
        if first.time > start:
            raise InsufficientPrices(
                f"Unable to map prices; first candle for {exchange} {symbol} at "
                f"{Timestamp_.format(first.time)} but requested start at "
                f"{Timestamp_.format(start)}"
            )
        if last.time < end - interval:
            raise InsufficientPrices(
                f"Unable to map prices; last candle for {exchange} {symbol} at "
                f"{Timestamp_.format(last.time)} but requested end at "
                f"{Timestamp_.format(end)}"
            )
