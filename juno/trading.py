from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from enum import IntEnum
from types import ModuleType
from typing import Optional, Sequence, Union

from juno import AssetInfo, Fill, Interval, Symbol, Symbol_, Timestamp, Timestamp_
from juno.asyncio import gather_dict
from juno.components import Chandler
from juno.math import annualized, round_half_down

_log = logging.getLogger(__name__)


class CloseReason(IntEnum):
    STRATEGY = 0
    STOP_LOSS = 1
    CANCELLED = 2
    TAKE_PROFIT = 3


class TradingMode(IntEnum):
    BACKTEST = 0
    PAPER = 1
    LIVE = 2


@dataclass(frozen=True)
class OpenPositionStats:
    cost: Decimal
    base_gain: Decimal


class Position(ModuleType):
    # TODO: Add support for external token fees (i.e BNB)
    @dataclass(frozen=True)
    class Long:
        exchange: str
        symbol: Symbol
        open_time: Timestamp
        open_fills: list[Fill]
        close_time: Timestamp
        close_fills: list[Fill]
        close_reason: CloseReason

        cost: Decimal
        base_gain: Decimal
        base_cost: Decimal
        gain: Decimal
        profit: Decimal
        roi: Decimal
        annualized_roi: Decimal
        dust: Decimal
        duration: Interval

        def __post_init__(self) -> None:
            if self.open_time < 0:
                raise ValueError("Open time cannot be negative")
            if self.close_time < self.open_time:
                raise ValueError("Close time cannot be less than start time")
            if len(self.open_fills) == 0:
                raise ValueError("A position must have at least one open fill")
            # Note that a position can have zero close fills if the position cannot be closed
            # anymore due to exchange filter requirements. Assume funds lost in this case.

        @staticmethod
        def build(
            exchange: str,
            symbol: Symbol,
            open_time: Timestamp,
            open_fills: list[Fill],
            close_time: Timestamp,
            close_fills: list[Fill],
            close_reason: CloseReason,
            base_asset_info: AssetInfo,
            quote_asset_info: AssetInfo,
        ) -> Position.Long:
            base_asset, quote_asset = Symbol_.assets(symbol)
            cost = Fill.total_quote(open_fills)
            gain = round_half_down(
                Fill.total_quote(close_fills)
                - Fill.total_quote_fee(close_fills, Symbol_.quote_asset(symbol), quote_asset_info),
                quote_asset_info.precision,
            )
            profit = gain - cost
            roi = profit / cost
            duration = close_time - open_time
            base_gain = round_half_down(
                Fill.total_size(open_fills)
                - Fill.total_fee(open_fills, base_asset)
                - Fill.total_base_fee_for_quote_asset(open_fills, quote_asset, base_asset_info),
                base_asset_info.precision,
            )
            base_cost = Fill.total_size(close_fills)

            return Position.Long(
                exchange=exchange,
                symbol=symbol,
                open_time=open_time,
                open_fills=open_fills,
                close_time=close_time,
                close_fills=close_fills,
                close_reason=close_reason,
                cost=cost,
                gain=gain,
                base_gain=base_gain,
                base_cost=base_cost,
                profit=profit,
                roi=roi,
                annualized_roi=annualized(duration, roi),
                dust=base_gain - base_cost,
                duration=duration,
            )

    @dataclass(frozen=True)
    class OpenLong:
        exchange: str
        symbol: Symbol
        time: Timestamp
        fills: list[Fill]

        cost: Decimal
        base_gain: Decimal

        def __post_init__(self) -> None:
            if self.time < 0:
                raise ValueError("Time cannot be negative")

        @staticmethod
        def build(
            exchange: str,
            symbol: Symbol,
            time: Timestamp,
            fills: list[Fill],
            base_asset_info: AssetInfo,
        ) -> Position.OpenLong:
            base_asset, quote_asset = Symbol_.assets(symbol)
            return Position.OpenLong(
                exchange=exchange,
                symbol=symbol,
                time=time,
                fills=fills,
                cost=Fill.total_quote(fills),
                base_gain=(
                    Fill.total_size(fills)
                    - Fill.total_fee(fills, base_asset)
                    - Fill.total_base_fee_for_quote_asset(fills, quote_asset, base_asset_info)
                ),
            )

        def close(
            self,
            time: Timestamp,
            fills: list[Fill],
            reason: CloseReason,
            base_asset_info: AssetInfo,
            quote_asset_info: AssetInfo,
        ) -> Position.Long:
            return Position.Long.build(
                exchange=self.exchange,
                symbol=self.symbol,
                open_time=self.time,
                open_fills=self.fills,
                close_time=time,
                close_fills=fills,
                close_reason=reason,
                base_asset_info=base_asset_info,
                quote_asset_info=quote_asset_info,
            )

    @dataclass(frozen=True)
    class Short:
        exchange: str
        symbol: Symbol
        collateral: Decimal  # quote
        borrowed: Decimal  # base
        open_time: Timestamp
        open_fills: list[Fill]
        close_time: Timestamp
        close_fills: list[Fill]
        close_reason: CloseReason
        interest: Decimal  # base

        cost: Decimal
        base_gain: Decimal
        base_cost: Decimal
        gain: Decimal
        profit: Decimal
        roi: Decimal
        annualized_roi: Decimal
        dust: Decimal
        duration: Interval

        def __post_init__(self) -> None:
            if self.open_time < 0:
                raise ValueError("Open time cannot be negative")
            if self.close_time < self.open_time:
                raise ValueError("Close time cannot be less than start time")
            if len(self.open_fills) == 0:
                raise ValueError("A position must have at least one open fill")
            # Note that a position can have zero close fills if the position cannot be closed
            # anymore due to exchange filter requirements. Assume funds lost in this case.

        @staticmethod
        def build(
            exchange: str,
            symbol: Symbol,
            collateral: Decimal,  # quote
            borrowed: Decimal,  # base
            open_time: Timestamp,
            open_fills: list[Fill],
            close_time: Timestamp,
            close_fills: list[Fill],
            close_reason: CloseReason,
            interest: Decimal,  # base
            quote_asset_info: AssetInfo,
        ) -> Position.Short:
            quote_asset = Symbol_.quote_asset(symbol)
            cost = collateral
            gain = round_half_down(
                Fill.total_quote(open_fills)
                - Fill.total_quote_fee(open_fills, quote_asset, quote_asset_info)
                + collateral
                - Fill.total_quote(close_fills)
                - Fill.total_quote_fee(close_fills, quote_asset, quote_asset_info),
                quote_asset_info.precision,
            )
            profit = gain - cost
            # TODO: Because we don't simulate margin call liquidation, ROI can go negative.
            # For now, we simply cap the value to min -1.
            roi = max(profit / cost, Decimal("-1.0"))
            duration = close_time - open_time
            base_gain = borrowed
            base_cost = borrowed

            return Position.Short(
                exchange=exchange,
                symbol=symbol,
                collateral=collateral,
                borrowed=borrowed,
                open_time=open_time,
                open_fills=open_fills,
                close_time=close_time,
                close_fills=close_fills,
                close_reason=close_reason,
                interest=interest,
                cost=cost,
                gain=gain,
                base_gain=base_gain,
                base_cost=base_cost,
                profit=profit,
                roi=roi,
                annualized_roi=annualized(duration, roi),
                dust=base_gain - base_cost,
                duration=duration,
            )

    @dataclass(frozen=True)
    class OpenShort:
        exchange: str
        symbol: Symbol
        collateral: Decimal
        borrowed: Decimal
        time: Timestamp
        fills: list[Fill]

        cost: Decimal
        base_gain: Decimal

        def __post_init__(self) -> None:
            if self.time < 0:
                raise ValueError("Time cannot be negative")

        @staticmethod
        def build(
            exchange: str,
            symbol: Symbol,
            collateral: Decimal,
            borrowed: Decimal,
            time: Timestamp,
            fills: list[Fill],
        ) -> Position.OpenShort:
            return Position.OpenShort(
                exchange=exchange,
                symbol=symbol,
                collateral=collateral,
                borrowed=borrowed,
                time=time,
                fills=fills,
                cost=collateral,
                base_gain=borrowed,
            )

        def close(
            self,
            interest: Decimal,
            time: Timestamp,
            fills: list[Fill],
            reason: CloseReason,
            quote_asset_info: AssetInfo,
        ) -> Position.Short:
            return Position.Short.build(
                exchange=self.exchange,
                symbol=self.symbol,
                collateral=self.collateral,
                borrowed=self.borrowed,
                open_time=self.time,
                open_fills=self.fills,
                close_time=time,
                close_fills=fills,
                close_reason=reason,
                interest=interest,
                quote_asset_info=quote_asset_info,
            )

    Any = Union[Long, OpenLong, OpenShort, Short]
    Open = Union[OpenLong, OpenShort]
    Closed = Union[Long, Short]


@dataclass(frozen=True)
class TradingSummary:
    start: Timestamp
    end: Timestamp
    starting_assets: dict[str, Decimal]
    positions: list[Position.Closed]

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError("Trading start time cannot be negative")
        if self.end < self.start:
            raise ValueError("Trading end time cannot be earlier than start time")
        if len(self.starting_assets) == 0:
            raise ValueError("Cannot trade without any starting asset")
        if any(amount <= 0 for amount in self.starting_assets.values()):
            raise ValueError("Starting asset value cannot be zero or negative")

    @property
    def profit(self) -> Decimal:
        return sum((p.profit for p in self.positions), Decimal("0.0"))


class StartMixin(ABC):
    @property
    @abstractmethod
    def chandler(self) -> Chandler:
        pass

    async def request_candle_start(
        self,
        start: Optional[Timestamp],
        exchange: str,
        symbols: Sequence[Symbol],
        interval: Interval,
    ) -> Timestamp:
        """Figures out an appropriate candle start time based on the requested start.
        If no specific start is requested, finds the earliest start of the interval where all
        candle intervals are available.
        If start is specified, floors the time to interval if interval is <= Interval_.DAY,
        otherwise floors to Interval_.DAY.
        """
        if len(symbols) == 0:
            raise ValueError("Must have at least one symbol for requesting start")
        if start is not None and start < 0:
            raise ValueError("Start cannot be negative")

        if start is None:
            symbol_first_candles = await gather_dict(
                {s: self.chandler.get_first_candle(exchange, s, interval) for s in symbols}
            )
            latest_symbol, latest_first_candle = max(
                symbol_first_candles.items(),
                key=lambda x: x[1].time,
            )

            result = latest_first_candle.time

            # If available, take also into account the time of the first smallest candle. This is
            # because the smallest candle may start later than the first requested interval candle.
            #
            # For example, first Binance eth-btc:
            # - 1w candle starts at 2017-07-10
            # - 1d candle starts at 2017-07-14
            #
            # Mapping daily prices for statistics would fail if we chose 2017-07-10 as the start.
            all_intervals = self.chandler.list_candle_intervals(exchange)
            smallest_interval = next(iter(all_intervals)) if len(all_intervals) > 0 else interval

            if interval != smallest_interval:
                smallest_latest_first_candle = await self.chandler.get_first_candle(
                    exchange, latest_symbol, smallest_interval
                )
                if smallest_latest_first_candle.time > latest_first_candle.time:
                    result += interval
        else:
            result = Timestamp_.floor(start, interval)

        if start is None:
            _log.info(f"start not specified; start set to {Timestamp_.format(result)}")
        elif result != start:
            _log.info(
                f"start specified as {Timestamp_.format(start)}; adjusted to "
                f"{Timestamp_.format(result)}"
            )
        else:
            _log.info(f"start specified as {Timestamp_.format(start)}; no adjustment needed")
        return result
