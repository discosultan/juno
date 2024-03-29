import asyncio
import logging
from decimal import Decimal
from typing import Collection, Iterable, Optional

from juno import Asset, Candle, Interval, Interval_, Symbol, Symbol_, Timestamp, Timestamp_
from juno.asyncio import gather_dict
from juno.components import Chandler, Informant
from juno.contextlib import AsyncContextManager
from juno.math import floor_multiple

_log = logging.getLogger(__name__)


class InsufficientPrices(Exception):
    pass


class Prices(AsyncContextManager):
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

    async def map_asset_prices_for_timestamp(
        self,
        exchange: str,
        assets: Collection[Asset],
        time: Timestamp,
        target_asset: Asset = "usdt",
        # If False, will raise an exception on missing price. If True, will set missing price to
        # Decimal("NaN")
        ignore_missing_price: bool = False,
    ) -> dict[Asset, Decimal]:
        """Creates a mapping of assets to target asset price."""
        intervals = self._chandler.list_candle_intervals(exchange)
        intervals.sort()
        interval = Interval_.DAY
        time = floor_multiple(time, interval)

        supported_symbols = set(self._informant.list_symbols(exchange))

        async def symbol_price(asset: Asset) -> Decimal:
            symbol = f"{asset}-{target_asset}"
            if symbol in supported_symbols:
                candles = await self._chandler.list_candles(
                    exchange=exchange,
                    symbol=symbol,
                    interval=interval,
                    start=time,
                    end=time + interval,
                )
                if len(candles) == 0:
                    if ignore_missing_price:
                        return Decimal("NaN")
                    else:
                        raise RuntimeError(f"Missing price for {symbol}")
                else:
                    return candles[0].open
            elif (reverse_symbol := Symbol_.swap(symbol)) in supported_symbols:
                candles = await self._chandler.list_candles(
                    exchange=exchange,
                    symbol=reverse_symbol,
                    interval=interval,
                    start=time,
                    end=time + interval,
                )
                if len(candles) == 0:
                    if ignore_missing_price:
                        return Decimal("NaN")
                    else:
                        raise RuntimeError(f"Missing price for {reverse_symbol}")
                else:
                    return Decimal("1.0") / candles[0].open
            else:
                if ignore_missing_price:
                    return Decimal("NaN")
                else:
                    raise RuntimeError(
                        f"Neither {symbol} nor {reverse_symbol} found in supported symbols."
                    )

        symbol_prices: dict[Asset, Decimal] = await gather_dict(
            {asset: symbol_price(asset) for asset in assets if asset != target_asset}
        )

        return {asset: symbol_prices.get(asset, Decimal("1.0")) for asset in assets}

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
                f"Unable to map prices; first {exchange} {symbol} {Interval_.format(interval)} "
                f"candle at {Timestamp_.format(first.time)} but requested start at "
                f"{Timestamp_.format(start)}"
            )
        if last.time < end - interval:
            raise InsufficientPrices(
                f"Unable to map prices; last {exchange} {symbol} {Interval_.format(interval)} "
                f"candle at {Timestamp_.format(last.time)} but requested end at "
                f"{Timestamp_.format(end)}"
            )
