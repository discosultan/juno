from __future__ import annotations

import itertools
import logging
import statistics
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal, Overflow
from types import ModuleType
from typing import Dict, Iterable, List, Optional, Union

from juno import Candle, Fees, Fill, Filters, Interval, OrderException, Timestamp
from juno.brokers import Broker
from juno.components import Informant
from juno.exchanges import Exchange
from juno.math import ceil_multiple, round_down, round_half_up
from juno.time import HOUR_MS, YEAR_MS
from juno.utils import unpack_symbol

_log = logging.getLogger(__name__)


class Position(ModuleType):
    # TODO: Add support for external token fees (i.e BNB)
    # Note that we cannot set the dataclass as frozen because that would break JSON
    # deserialization.
    @dataclass
    class Long:
        symbol: str
        open_time: Timestamp
        open_fills: List[Fill]
        close_time: Timestamp
        close_fills: List[Fill]

        @property
        def cost(self) -> Decimal:
            return Fill.total_quote(self.open_fills)

        @property
        def base_gain(self) -> Decimal:
            return Fill.total_size(self.open_fills) - Fill.total_fee(self.open_fills)

        @property
        def base_cost(self) -> Decimal:
            return Fill.total_size(self.close_fills)

        @property
        def gain(self) -> Decimal:
            return Fill.total_quote(self.close_fills) - Fill.total_fee(self.close_fills)

        @property
        def profit(self) -> Decimal:
            return self.gain - self.cost

        @property
        def roi(self) -> Decimal:
            return self.profit / self.cost

        @property
        def annualized_roi(self) -> Decimal:
            return _annualized_roi(self.duration, self.roi)

        @property
        def dust(self) -> Decimal:
            return (
                Fill.total_size(self.open_fills)
                - Fill.total_fee(self.open_fills)
                - Fill.total_size(self.close_fills)
            )

        @property
        def duration(self) -> Interval:
            return self.close_time - self.open_time

    @dataclass
    class OpenLong:
        symbol: str
        time: Timestamp
        fills: List[Fill]

        def close(self, time: Timestamp, fills: List[Fill]) -> Position.Long:
            return Position.Long(
                symbol=self.symbol,
                open_time=self.time,
                open_fills=self.fills,
                close_time=time,
                close_fills=fills,
            )

        @property
        def cost(self) -> Decimal:
            return Fill.total_quote(self.fills)

        @property
        def base_gain(self) -> Decimal:
            return Fill.total_size(self.fills) - Fill.total_fee(self.fills)

    @dataclass
    class Short:
        symbol: str
        collateral: Decimal  # quote
        borrowed: Decimal  # base
        open_time: Timestamp
        open_fills: List[Fill]
        close_time: Timestamp
        close_fills: List[Fill]
        interest: Decimal  # base

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
                - Fill.total_fee(self.open_fills)
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
            return max(self.profit / self.cost, Decimal('-1.0'))

        @property
        def annualized_roi(self) -> Decimal:
            return _annualized_roi(self.duration, self.roi)

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
        symbol: str
        collateral: Decimal
        borrowed: Decimal
        time: Timestamp
        fills: List[Fill]

        def close(self, interest: Decimal, time: Timestamp, fills: List[Fill]) -> Position.Short:
            return Position.Short(
                symbol=self.symbol,
                collateral=self.collateral,
                borrowed=self.borrowed,
                open_time=self.time,
                open_fills=self.fills,
                close_time=time,
                close_fills=fills,
                interest=interest,
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
@dataclass(init=False)
class TradingSummary:
    start: Timestamp
    # TODO: We may want to store a dictionary of quote assets instead to support more pairs.
    # Make sure to update `_get_asset_performance` in statistics.
    quote: Decimal
    quote_asset: str

    _long_positions: List[Position.Long]
    _short_positions: List[Position.Short]
    _drawdowns: List[Decimal]
    _max_drawdown: Decimal = Decimal('0.0')
    _mean_drawdown: Decimal = Decimal('0.0')

    # TODO: Should we add +interval like we do for summary? Or rather change summary to exclude
    # +interval. Also needs to be adjusted in Rust code.
    end: Optional[Timestamp] = None

    _drawdowns_dirty: bool = True

    def __init__(self, start: Timestamp, quote: Decimal, quote_asset: str) -> None:
        self.start = start
        self.quote = quote
        self.quote_asset = quote_asset

        self._long_positions = []
        self._short_positions = []
        self._drawdowns = []

    def append_position(self, pos: Position.Closed) -> None:
        if isinstance(pos, Position.Long):
            self._long_positions.append(pos)
        elif isinstance(pos, Position.Short):
            self._short_positions.append(pos)
        else:
            raise NotImplementedError()
        self._drawdowns_dirty = True

    def get_positions(self) -> Iterable[Position.Closed]:
        return sorted(
            itertools.chain(self._long_positions, self._short_positions),
            key=lambda p: p.open_time,
        )

    def get_long_positions(self) -> Iterable[Position.Long]:
        return self._long_positions

    def get_short_positions(self) -> Iterable[Position.Short]:
        return self._short_positions

    def finish(self, end: Timestamp) -> None:
        if self.end is None:
            self.end = end
        else:
            self.end = max(end, self.end)

    @property
    def cost(self) -> Decimal:
        return self.quote

    @property
    def gain(self) -> Decimal:
        return self.quote + self.profit

    @property
    def profit(self) -> Decimal:
        return sum((p.profit for p in self.get_positions()), Decimal('0.0'))

    @property
    def roi(self) -> Decimal:
        return self.profit / self.cost

    @property
    def annualized_roi(self) -> Decimal:
        return _annualized_roi(self.duration, self.roi)

    @property
    def duration(self) -> Interval:
        return 0 if self.end is None else self.end - self.start

    @property
    def num_positions(self) -> int:
        return len(self._long_positions) + len(self._short_positions)

    @property
    def num_long_positions(self) -> int:
        return len(self._long_positions)

    @property
    def num_short_positions(self) -> int:
        return len(self._short_positions)

    @staticmethod
    def _num_positions_in_profit(positions: Iterable[Position.Closed]) -> int:
        return sum(1 for p in positions if p.profit >= 0)

    @property
    def num_positions_in_profit(self) -> int:
        return TradingSummary._num_positions_in_profit(self.get_positions())

    @property
    def num_long_positions_in_profit(self) -> int:
        return TradingSummary._num_positions_in_profit(self._long_positions)

    @property
    def num_short_positions_in_profit(self) -> int:
        return TradingSummary._num_positions_in_profit(self._short_positions)

    @staticmethod
    def _num_positions_in_loss(positions: Iterable[Position.Closed]) -> int:
        return sum(1 for p in positions if p.profit < 0)

    @property
    def num_positions_in_loss(self) -> int:
        return TradingSummary._num_positions_in_loss(self.get_positions())

    @property
    def num_long_positions_in_loss(self) -> int:
        return TradingSummary._num_positions_in_loss(self._long_positions)

    @property
    def num_short_positions_in_loss(self) -> int:
        return TradingSummary._num_positions_in_loss(self._short_positions)

    @staticmethod
    def _mean_position_profit(positions: Iterable[Position.Closed]) -> Decimal:
        profits = [x.profit for x in positions]
        if len(profits) == 0:
            return Decimal('0.0')
        return statistics.mean(profits)

    @property
    def mean_position_profit(self) -> Decimal:
        return TradingSummary._mean_position_profit(self.get_positions())

    @property
    def mean_long_position_profit(self) -> Decimal:
        return TradingSummary._mean_position_profit(self._long_positions)

    @property
    def mean_short_position_profit(self) -> Decimal:
        return TradingSummary._mean_position_profit(self._short_positions)

    @staticmethod
    def _mean_position_duration(positions: Iterable[Position.Closed]) -> Interval:
        durations = [x.duration for x in positions]
        if len(durations) == 0:
            return 0
        return int(statistics.mean(durations))

    @property
    def mean_position_duration(self) -> Interval:
        return TradingSummary._mean_position_duration(self.get_positions())

    @property
    def mean_long_position_duration(self) -> Interval:
        return TradingSummary._mean_position_duration(self._long_positions)

    @property
    def mean_short_position_duration(self) -> Interval:
        return TradingSummary._mean_position_duration(self._short_positions)

    # @property
    # def drawdowns(self) -> List[Decimal]:
    #     self._calc_drawdowns_if_stale()
    #     return self._drawdowns

    @property
    def max_drawdown(self) -> Decimal:
        self._calc_drawdowns_if_stale()
        return self._max_drawdown

    @property
    def mean_drawdown(self) -> Decimal:
        self._calc_drawdowns_if_stale()
        return self._mean_drawdown

    def _calc_drawdowns_if_stale(self) -> None:
        if not self._drawdowns_dirty:
            return

        quote = self.quote
        max_quote = quote
        self._max_drawdown = Decimal('0.0')
        sum_drawdown = Decimal('0.0')
        self._drawdowns.clear()
        self._drawdowns.append(Decimal('0.0'))
        for pos in self.get_positions():
            quote += pos.profit
            max_quote = max(max_quote, quote)
            drawdown = Decimal('1.0') - quote / max_quote
            self._drawdowns.append(drawdown)
            sum_drawdown += drawdown
            self._max_drawdown = max(self._max_drawdown, drawdown)
        self._mean_drawdown = sum_drawdown / len(self._drawdowns)

        self._drawdowns_dirty = False

    def calculate_hodl_profit(
        self, first_candle: Candle, last_candle: Candle, fees: Fees, filters: Filters
    ) -> Decimal:
        base_hodl = filters.size.round_down(self.quote / first_candle.close)
        base_hodl -= round_half_up(base_hodl * fees.taker, filters.base_precision)
        quote_hodl = filters.size.round_down(base_hodl) * last_candle.close
        quote_hodl -= round_half_up(quote_hodl * fees.taker, filters.quote_precision)
        return quote_hodl - self.quote


# Ref: https://www.investopedia.com/articles/basics/10/guide-to-calculating-roi.asp
def _annualized_roi(duration: int, roi: Decimal) -> Decimal:
    assert roi >= -1
    n = Decimal(duration) / YEAR_MS
    if n == 0:
        return Decimal('0.0')
    try:
        return (1 + roi)**(1 / n) - 1
    except Overflow:
        return Decimal('Inf')


class SimulatedPositionMixin(ABC):
    @property
    @abstractmethod
    def informant(self) -> Informant:
        pass

    def open_simulated_long_position(
        self, candle: Candle, exchange: str, symbol: str, quote: Decimal
    ) -> Position.OpenLong:
        price = candle.close
        base_asset, _ = unpack_symbol(symbol)
        fees, filters = self.informant.get_fees_filters(exchange, symbol)

        size = filters.size.round_down(quote / price)
        if size == 0:
            raise OrderException()
        quote = round_down(price * size, filters.quote_precision)
        fee = round_half_up(size * fees.taker, filters.base_precision)

        return Position.OpenLong(
            symbol=symbol,
            time=candle.time,
            fills=[Fill(
                price=price, size=size, quote=quote, fee=fee, fee_asset=base_asset
            )],
        )

    # TODO: Take exchange and symbol from position?
    def close_simulated_long_position(
        self, candle: Candle, position: Position.OpenLong, exchange: str
    ) -> Position.Long:
        price = candle.close
        _, quote_asset = unpack_symbol(position.symbol)
        fees, filters = self.informant.get_fees_filters(exchange, position.symbol)

        size = filters.size.round_down(position.base_gain)
        quote = round_down(price * size, filters.quote_precision)
        fee = round_half_up(quote * fees.taker, filters.quote_precision)

        return position.close(
            time=candle.time,
            fills=[Fill(
                price=price, size=size, quote=quote, fee=fee, fee_asset=quote_asset
            )],
        )

    def open_simulated_short_position(
        self, candle: Candle, exchange: str, symbol: str, collateral: Decimal
    ) -> Position.OpenShort:
        price = candle.close
        _, quote_asset = unpack_symbol(symbol)
        fees, filters = self.informant.get_fees_filters(exchange, symbol)
        margin_multiplier = self.informant.get_margin_multiplier(exchange)

        borrowed = _calculate_borrowed(filters, margin_multiplier, collateral, price)
        quote = round_down(price * borrowed, filters.quote_precision)
        fee = round_half_up(quote * fees.taker, filters.quote_precision)

        return Position.OpenShort(
            symbol=symbol,
            collateral=collateral,
            borrowed=borrowed,
            time=candle.time,
            fills=[Fill(
                price=price, size=borrowed, quote=quote, fee=fee, fee_asset=quote_asset
            )],
        )

    def close_simulated_short_position(
        self, candle: Candle, position: Position.OpenShort, exchange: str
    ) -> Position.Short:
        price = candle.close
        base_asset, _ = unpack_symbol(position.symbol)
        fees, filters = self.informant.get_fees_filters(exchange, position.symbol)
        borrow_info = self.informant.get_borrow_info(exchange, base_asset)

        interest = _calculate_interest(
            borrowed=position.borrowed,
            hourly_rate=borrow_info.hourly_interest_rate,
            start=position.time,
            end=candle.time,
        )
        size = position.borrowed + interest
        quote = round_down(price * size, filters.quote_precision)
        fee = round_half_up(size * fees.taker, filters.base_precision)
        size += fee

        return position.close(
            time=candle.time,
            interest=interest,
            fills=[Fill(
                price=price, size=size, quote=quote, fee=fee, fee_asset=base_asset
            )],
        )


class PositionMixin(ABC):
    @property
    @abstractmethod
    def informant(self) -> Informant:
        pass

    @property
    @abstractmethod
    def broker(self) -> Broker:
        pass

    @property
    @abstractmethod
    def exchanges(self) -> Dict[str, Exchange]:
        pass

    async def open_long_position(
        self, candle: Candle, exchange: str, symbol: str, quote: Decimal, test: bool
    ) -> Position.OpenLong:
        res = await self.broker.buy_by_quote(
            exchange=exchange,
            symbol=symbol,
            quote=quote,
            test=test,
        )

        return Position.OpenLong(
            symbol=symbol,
            time=candle.time,
            fills=res.fills,
        )

    async def close_long_position(
        self, candle: Candle, position: Position.OpenLong, exchange: str, test: bool
    ) -> Position.Long:
        res = await self.broker.sell(
            exchange=exchange,
            symbol=position.symbol,
            size=position.base_gain,
            test=test,
        )

        return position.close(
            time=candle.time,
            fills=res.fills,
        )

    async def open_short_position(
        self, candle: Candle, exchange: str, symbol: str, collateral: Decimal, test: bool
    ) -> Position.OpenShort:
        price = candle.close
        base_asset, quote_asset = unpack_symbol(symbol)
        _, filters = self.informant.get_fees_filters(exchange, symbol)
        margin_multipler = self.informant.get_margin_multiplier(exchange)
        exchange_instance = self.exchanges[exchange]

        if test:
            borrowed = _calculate_borrowed(filters, margin_multipler, collateral, price)
        else:
            _log.info(f'transferring {collateral} {quote_asset} to margin account')
            await exchange_instance.transfer(quote_asset, collateral, margin=True)
            borrowed = await exchange_instance.get_max_borrowable(quote_asset)
            _log.info(f'borrowing {borrowed} {base_asset} from exchange')
            await exchange_instance.borrow(asset=base_asset, size=borrowed)

        res = await self.broker.sell(
            exchange=exchange,
            symbol=symbol,
            size=borrowed,
            test=test,
            margin=not test,
        )

        return Position.OpenShort(
            symbol=symbol,
            collateral=collateral,
            borrowed=borrowed,
            time=candle.time,
            fills=res.fills,
        )

    async def close_short_position(
        self, candle: Candle, position: Position.OpenShort, exchange: str, test: bool
    ) -> Position.Short:
        base_asset, quote_asset = unpack_symbol(position.symbol)
        fees, filters = self.informant.get_fees_filters(exchange, position.symbol)
        borrow_info = self.informant.get_borrow_info(exchange, base_asset)
        exchange_instance = self.exchanges[exchange]

        interest = (
            _calculate_interest(
                borrowed=position.borrowed,
                hourly_rate=borrow_info.hourly_interest_rate,
                start=position.time,
                end=candle.time,
            ) if test
            else (await exchange_instance.map_balances(margin=True))[base_asset].interest
        )
        size = position.borrowed + interest
        fee = round_half_up(size * fees.taker, filters.base_precision)
        size = filters.size.round_up(size + fee)
        res = await self.broker.buy(
            exchange=exchange,
            symbol=position.symbol,
            size=size,
            test=test,
            margin=not test,
        )
        closed_position = position.close(
            interest=interest,
            time=candle.time,
            fills=res.fills,
        )
        if not test:
            _log.info(
                f'repaying {position.borrowed} + {interest} {base_asset} to exchange'
            )
            await exchange_instance.repay(base_asset, position.borrowed + interest)
            # Validate!
            # TODO: Remove if known to work or pay extra if needed.
            new_balance = (await exchange_instance.map_balances(margin=True))[base_asset]
            if new_balance.repay != 0:
                _log.error(f'did not repay enough; balance {new_balance}')
                assert new_balance.repay == 0

            transfer = closed_position.collateral + closed_position.profit
            _log.info(f'transferring {transfer} {quote_asset} to spot account')
            await exchange_instance.transfer(quote_asset, transfer, margin=False)

        return closed_position


def _calculate_borrowed(
    filters: Filters, margin_multiplier: int, collateral: Decimal, price: Decimal
) -> Decimal:
    collateral_size = filters.size.round_down(collateral / price)
    if collateral_size == 0:
        raise OrderException('Collateral base size 0')
    borrowed = collateral_size * (margin_multiplier - 1)
    if borrowed == 0:
        raise OrderException('Borrowed 0; incorrect margin multiplier?')
    return borrowed


def _calculate_interest(borrowed: Decimal, hourly_rate: Decimal, start: int, end: int) -> Decimal:
    duration = ceil_multiple(end - start, HOUR_MS) // HOUR_MS
    return borrowed * duration * hourly_rate
