from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import IntEnum
from types import ModuleType
from typing import Iterable, Optional, Sequence, Union

from juno import Fill, Interval, Timestamp
from juno.asyncio import gather_dict
from juno.components import Chandler
from juno.math import annualized, floor_multiple_offset
from juno.time import strftimestamp
from juno.utils import unpack_base_asset, unpack_quote_asset

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


class Position(ModuleType):
    # TODO: Add support for external token fees (i.e BNB)
    # Note that we cannot set the dataclass as frozen because that would break JSON
    # deserialization.
    @dataclass
    class Long:
        exchange: str
        symbol: str
        open_time: Timestamp
        open_fills: list[Fill]
        close_time: Timestamp
        close_fills: list[Fill]
        close_reason: CloseReason

        @property
        def quote_delta(self) -> Decimal:
            return self.gain

        @property
        def cost(self) -> Decimal:
            return Fill.total_quote(self.open_fills)

        @property
        def base_gain(self) -> Decimal:
            return Fill.total_size(self.open_fills) - Fill.total_fee(
                self.open_fills, unpack_base_asset(self.symbol)
            )

        @property
        def base_cost(self) -> Decimal:
            return Fill.total_size(self.close_fills)

        @property
        def gain(self) -> Decimal:
            return Fill.total_quote(self.close_fills) - Fill.total_fee(
                self.close_fills, unpack_quote_asset(self.symbol)
            )

        @property
        def profit(self) -> Decimal:
            return self.gain - self.cost

        @property
        def roi(self) -> Decimal:
            return self.profit / self.cost

        @property
        def annualized_roi(self) -> Decimal:
            return annualized(self.duration, self.roi)

        @property
        def dust(self) -> Decimal:
            return (
                Fill.total_size(self.open_fills)
                - Fill.total_fee(self.open_fills, unpack_base_asset(self.symbol))
                - Fill.total_size(self.close_fills)
            )

        @property
        def duration(self) -> Interval:
            return self.close_time - self.open_time

    @dataclass
    class OpenLong:
        exchange: str
        symbol: str
        time: Timestamp
        fills: list[Fill]

        def close(self, time: Timestamp, fills: list[Fill], reason: CloseReason) -> Position.Long:
            return Position.Long(
                exchange=self.exchange,
                symbol=self.symbol,
                open_time=self.time,
                open_fills=self.fills,
                close_time=time,
                close_fills=fills,
                close_reason=reason,
            )

        @property
        def quote_delta(self) -> Decimal:
            return -self.cost

        @property
        def cost(self) -> Decimal:
            return Fill.total_quote(self.fills)

        @property
        def base_gain(self) -> Decimal:
            return Fill.total_size(self.fills) - Fill.total_fee(
                self.fills, unpack_base_asset(self.symbol)
            )

    @dataclass
    class Short:
        exchange: str
        symbol: str
        collateral: Decimal  # quote
        borrowed: Decimal  # base
        open_time: Timestamp
        open_fills: list[Fill]
        close_time: Timestamp
        close_fills: list[Fill]
        close_reason: CloseReason
        interest: Decimal  # base

        @property
        def quote_delta(self) -> Decimal:
            return -Fill.total_quote(self.close_fills)

        @property
        def cost(self) -> Decimal:
            return self.collateral

        @property
        def base_gain(self) -> Decimal:
            return self.borrowed

        @property
        def base_cost(self) -> Decimal:
            return self.borrowed

        @property
        def gain(self) -> Decimal:
            return (
                Fill.total_quote(self.open_fills)
                - Fill.total_fee(self.open_fills, unpack_quote_asset(self.symbol))
                + self.collateral
                - Fill.total_quote(self.close_fills)
            )

        @property
        def profit(self) -> Decimal:
            return self.gain - self.cost

        @property
        def roi(self) -> Decimal:
            # TODO: Because we don't simulate margin call liquidation, ROI can go negative.
            # For now, we simply cap the value to min -1.
            return max(self.profit / self.cost, Decimal("-1.0"))

        @property
        def annualized_roi(self) -> Decimal:
            return annualized(self.duration, self.roi)

        # TODO: implement
        # @property
        # def dust(self) -> Decimal:
        #     return (
        #         Fill.total_size(self.open_fills)
        #         - Fill.total_fee(self.open_fills)
        #         - Fill.total_size(self.close_fills)
        #     )

        @property
        def duration(self) -> Interval:
            return self.close_time - self.open_time

    @dataclass
    class OpenShort:
        exchange: str
        symbol: str
        collateral: Decimal
        borrowed: Decimal
        time: Timestamp
        fills: list[Fill]

        def close(
            self, interest: Decimal, time: Timestamp, fills: list[Fill], reason: CloseReason
        ) -> Position.Short:
            return Position.Short(
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
            )

        @property
        def quote_delta(self) -> Decimal:
            return Fill.total_quote(self.fills) - Fill.total_fee(
                self.fills, unpack_quote_asset(self.symbol)
            )

        @property
        def cost(self) -> Decimal:
            return self.collateral

        @property
        def base_gain(self) -> Decimal:
            return self.borrowed

    Any = Union[Long, OpenLong, OpenShort, Short]
    Open = Union[OpenLong, OpenShort]
    Closed = Union[Long, Short]


# TODO: both positions and candles could theoretically grow infinitely
# TODO: include fees from other than base and quote assets (BNB, for example)
@dataclass
class TradingSummary:
    start: Timestamp
    # TODO: We may want to store a dictionary of quote assets instead to support more pairs.
    # Make sure to update `_get_asset_performance` in statistics.
    quote: Decimal
    quote_asset: str

    _positions: list[Position.Closed] = field(default_factory=list)

    end: Timestamp = -1

    def __post_init__(self):
        if self.end == -1:
            self.end = self.start

    @property
    def profit(self) -> Decimal:
        return sum((p.profit for p in self._positions), Decimal("0.0"))

    def append_position(self, pos: Position.Closed) -> None:
        self._positions.append(pos)
        self.finish(pos.close_time)

    def get_positions(
        self,
        type_: Optional[type[Position.Closed]] = None,
        reason: Optional[CloseReason] = None,
    ) -> Iterable[Position.Closed]:
        result = (p for p in self._positions)
        if type_ is not None:
            result = (p for p in result if isinstance(p, type_))
        if reason is not None:
            result = (p for p in result if p.close_reason is reason)
        return result

    def list_positions(
        self,
        type_: Optional[type[Position.Closed]] = None,
        reason: Optional[CloseReason] = None,
    ) -> list[Position.Closed]:
        return list(self.get_positions(type_, reason))

    def finish(self, end: Timestamp) -> None:
        self.end = max(end, self.end)


class StartMixin(ABC):
    @property
    @abstractmethod
    def chandler(self) -> Chandler:
        pass

    async def request_candle_start(
        self, start: Optional[Timestamp], exchange: str, symbols: Sequence[str], interval: int
    ) -> int:
        """Figures out an appropriate candle start time based on the requested start.
        If no specific start is requested, finds the earliest start of the interval where all
        candle intervals are available.
        If start is specified, floors the time to interval if interval is <= DAY_MS, otherwise
        floors to DAY_MS.
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
            all_intervals = self.chandler.map_candle_intervals(exchange).keys()
            smallest_interval = next(iter(all_intervals)) if len(all_intervals) > 0 else interval

            if interval != smallest_interval:
                smallest_latest_first_candle = await self.chandler.get_first_candle(
                    exchange, latest_symbol, smallest_interval
                )
                if smallest_latest_first_candle.time > latest_first_candle.time:
                    result += interval
        else:
            interval_offset = self.chandler.get_interval_offset(exchange, interval)
            result = floor_multiple_offset(start, interval, interval_offset)

        if start is None:
            _log.info(f"start not specified; start set to {strftimestamp(result)}")
        elif result != start:
            _log.info(
                f"start specified as {strftimestamp(start)}; adjusted to {strftimestamp(result)}"
            )
        else:
            _log.info(f"start specified as {strftimestamp(start)}; no adjustment needed")
        return result
