from __future__ import annotations

import asyncio
import itertools
import logging
import statistics
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal, Overflow
from enum import IntEnum
from types import ModuleType
from typing import Iterable, List, Optional, Type, Union

from juno import Candle, Fees, Fill, Filters, Interval, OrderException, Timestamp
from juno.brokers import Broker
from juno.components import Chandler, Informant, User
from juno.math import ceil_multiple, round_down, round_half_up
from juno.time import HOUR_MS, MIN_MS, YEAR_MS, strftimestamp, time_ms
from juno.utils import extract_public, unpack_symbol

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


@dataclass
class StopLoss:
    threshold: Decimal = Decimal('0.0')  # 0 means disabled.
    trail: bool = True
    _close_at_position: Decimal = Decimal('0.0')
    _highest_close_since_position = Decimal('0.0')
    _lowest_close_since_position = Decimal('Inf')
    _close: Decimal = Decimal('0.0')

    @staticmethod
    def is_valid(threshold: Decimal) -> bool:
        return 0 <= threshold < 1

    @property
    def upside_hit(self) -> bool:
        return (
            self.threshold > 0
            and (
                self._close
                <= (self._highest_close_since_position if self.trail else self._close_at_position)
                * (1 - self.threshold)
            )
        )

    @property
    def downside_hit(self) -> bool:
        return (
            self.threshold > 0
            and (
                self._close
                >= (self._lowest_close_since_position if self.trail else self._close_at_position)
                * (1 + self.threshold)
            )
        )

    def clear(self, candle: Candle) -> None:
        self._close_at_position = candle.close
        self._highest_close_since_position = candle.close
        self._lowest_close_since_position = candle.close

    def update(self, candle: Candle) -> None:
        self._close = candle.close
        self._highest_close_since_position = max(self._highest_close_since_position, candle.close)
        self._lowest_close_since_position = min(self._lowest_close_since_position, candle.close)


@dataclass
class TakeProfit:
    threshold: Decimal = Decimal('0.0')  # 0 means disabled.
    _close_at_position: Decimal = Decimal('0.0')
    _close: Decimal = Decimal('0.0')

    @staticmethod
    def is_valid(threshold: Decimal) -> bool:
        return 0 <= threshold

    @property
    def upside_hit(self) -> bool:
        return (
            self.threshold > 0
            and self._close >= self._close_at_position * (1 + self.threshold)
        )

    @property
    def downside_hit(self) -> bool:
        return (
            self.threshold > 0
            and self._close <= self._close_at_position * (1 - self.threshold)
        )

    def clear(self, candle: Candle) -> None:
        self._close_at_position = candle.close

    def update(self, candle: Candle) -> None:
        self._close = candle.close


class Position(ModuleType):
    # TODO: Add support for external token fees (i.e BNB)
    # Note that we cannot set the dataclass as frozen because that would break JSON
    # deserialization.
    @dataclass
    class Long:
        exchange: str
        symbol: str
        open_time: Timestamp
        open_fills: List[Fill]
        close_time: Timestamp
        close_fills: List[Fill]
        close_reason: CloseReason

        def quote_delta(self) -> Decimal:
            return self.gain

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
        exchange: str
        symbol: str
        time: Timestamp
        fills: List[Fill]

        def close(
            self, time: Timestamp, fills: List[Fill], reason: CloseReason
        ) -> Position.Long:
            return Position.Long(
                exchange=self.exchange,
                symbol=self.symbol,
                open_time=self.time,
                open_fills=self.fills,
                close_time=time,
                close_fills=fills,
                close_reason=reason,
            )

        def quote_delta(self) -> Decimal:
            return -self.cost

        @property
        def cost(self) -> Decimal:
            return Fill.total_quote(self.fills)

        @property
        def base_gain(self) -> Decimal:
            return Fill.total_size(self.fills) - Fill.total_fee(self.fills)

    @dataclass
    class Short:
        exchange: str
        symbol: str
        collateral: Decimal  # quote
        borrowed: Decimal  # base
        open_time: Timestamp
        open_fills: List[Fill]
        close_time: Timestamp
        close_fills: List[Fill]
        close_reason: CloseReason
        interest: Decimal  # base

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
        exchange: str
        symbol: str
        collateral: Decimal
        borrowed: Decimal
        time: Timestamp
        fills: List[Fill]

        def close(
            self, interest: Decimal, time: Timestamp, fills: List[Fill],
            reason: CloseReason
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

        def quote_delta(self) -> Decimal:
            return Fill.total_quote(self.fills) - Fill.total_fee(self.fills)

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
@dataclass
class TradingSummary:
    start: Timestamp
    # TODO: We may want to store a dictionary of quote assets instead to support more pairs.
    # Make sure to update `_get_asset_performance` in statistics.
    quote: Decimal
    quote_asset: str

    _positions: List[Position.Closed] = field(default_factory=list)
    _drawdowns: List[Decimal] = field(default_factory=list)
    _max_drawdown: Decimal = Decimal('0.0')
    _mean_drawdown: Decimal = Decimal('0.0')

    end: Optional[Timestamp] = None

    _drawdowns_dirty: bool = True

    def append_position(self, pos: Position.Closed) -> None:
        self._positions.append(pos)
        self.finish(pos.close_time)
        self._drawdowns_dirty = True

    def get_positions(
        self,
        type_: Optional[Type[Position.Closed]] = None,
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
        type_: Optional[Type[Position.Closed]] = None,
        reason: Optional[CloseReason] = None,
    ) -> List[Position.Closed]:
        return list(self.get_positions(type_, reason))

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
        return len(self._positions)

    @property
    def num_positions_in_profit(self) -> int:
        return TradingSummary._num_positions_in_profit(self.get_positions())

    @property
    def num_positions_in_loss(self) -> int:
        return TradingSummary._num_positions_in_loss(self.get_positions())

    @property
    def num_long_positions(self) -> int:
        return len(self.list_positions(type_=Position.Long))

    @property
    def num_long_positions_in_profit(self) -> int:
        return TradingSummary._num_positions_in_profit(self.get_positions(type_=Position.Long))

    @property
    def num_long_positions_in_loss(self) -> int:
        return TradingSummary._num_positions_in_loss(self.get_positions(type_=Position.Long))

    @property
    def num_short_positions(self) -> int:
        return len(self.list_positions(type_=Position.Short))

    @property
    def num_short_positions_in_profit(self) -> int:
        return TradingSummary._num_positions_in_profit(self.get_positions(type_=Position.Short))

    @property
    def num_short_positions_in_loss(self) -> int:
        return TradingSummary._num_positions_in_loss(self.get_positions(type_=Position.Short))

    @staticmethod
    def _num_positions_in_profit(positions: Iterable[Position.Closed]) -> int:
        return sum(1 for p in positions if p.profit >= 0)

    @staticmethod
    def _num_positions_in_loss(positions: Iterable[Position.Closed]) -> int:
        return sum(1 for p in positions if p.profit < 0)

    @property
    def num_take_profits(self) -> int:
        return sum(1 for p in self._positions if p.close_reason is CloseReason.TAKE_PROFIT)

    @property
    def num_stop_losses(self) -> int:
        return sum(1 for p in self._positions if p.close_reason is CloseReason.STOP_LOSS)

    @property
    def mean_position_profit(self) -> Decimal:
        return TradingSummary._mean_position_profit(self.get_positions())

    @property
    def mean_long_position_profit(self) -> Decimal:
        return TradingSummary._mean_position_profit(self.get_positions(type_=Position.Long))

    @property
    def mean_short_position_profit(self) -> Decimal:
        return TradingSummary._mean_position_profit(self.get_positions(type_=Position.Short))

    @staticmethod
    def _mean_position_profit(positions: Iterable[Position.Closed]) -> Decimal:
        profits = [x.profit for x in positions]
        if len(profits) == 0:
            return Decimal('0.0')
        return statistics.mean(profits)

    @property
    def mean_position_duration(self) -> Interval:
        return TradingSummary._mean_position_duration(self.get_positions())

    @property
    def mean_long_position_duration(self) -> Interval:
        return TradingSummary._mean_position_duration(self.get_positions(type_=Position.Long))

    @property
    def mean_short_position_duration(self) -> Interval:
        return TradingSummary._mean_position_duration(self.get_positions(type_=Position.Short))

    @staticmethod
    def _mean_position_duration(positions: Iterable[Position.Closed]) -> Interval:
        durations = [x.duration for x in positions]
        if len(durations) == 0:
            return 0
        return int(statistics.mean(durations))

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
        self, exchange: str, symbol: str, time: Timestamp, price: Decimal, quote: Decimal,
        log: bool = True
    ) -> Position.OpenLong:
        base_asset, _ = unpack_symbol(symbol)
        fees, filters = self.informant.get_fees_filters(exchange, symbol)

        size = filters.size.round_down(quote / price)
        if size == 0:
            raise OrderException()
        quote = round_down(price * size, filters.quote_precision)
        fee = round_half_up(size * fees.taker, filters.base_precision)

        open_position = Position.OpenLong(
            exchange=exchange,
            symbol=symbol,
            time=time,
            fills=[Fill(
                price=price, size=size, quote=quote, fee=fee, fee_asset=base_asset
            )],
        )
        if log:
            _log.info(f'{symbol} simulated long position opened at {strftimestamp(time)}')
        return open_position

    def close_simulated_long_position(
        self, position: Position.OpenLong, time: Timestamp, price: Decimal, reason: CloseReason,
        log: bool = True
    ) -> Position.Long:
        _, quote_asset = unpack_symbol(position.symbol)
        fees, filters = self.informant.get_fees_filters(position.exchange, position.symbol)

        size = filters.size.round_down(position.base_gain)
        quote = round_down(price * size, filters.quote_precision)
        fee = round_half_up(quote * fees.taker, filters.quote_precision)

        closed_position = position.close(
            time=time,
            fills=[Fill(
                price=price, size=size, quote=quote, fee=fee, fee_asset=quote_asset
            )],
            reason=reason,
        )
        if log:
            _log.info(
                f'{closed_position.symbol} simulated long position closed at '
                f'{strftimestamp(time)} due to {reason.name}'
            )
        return closed_position

    def open_simulated_short_position(
        self, exchange: str, symbol: str, time: Timestamp, price: Decimal, collateral: Decimal,
        log: bool = True
    ) -> Position.OpenShort:
        base_asset, quote_asset = unpack_symbol(symbol)
        fees, filters = self.informant.get_fees_filters(exchange, symbol)
        limit = self.informant.get_borrow_info(
            exchange=exchange, asset=base_asset, account=symbol
        ).limit
        # TODO: We could get a maximum margin multiplier from the exchange and use that but use the
        # lowers multiplier for now for reduced risk.
        margin_multiplier = 2
        # margin_multiplier = self.informant.get_margin_multiplier(exchange)

        borrowed = _calculate_borrowed(filters, margin_multiplier, limit, collateral, price)
        quote = round_down(price * borrowed, filters.quote_precision)
        fee = round_half_up(quote * fees.taker, filters.quote_precision)

        open_position = Position.OpenShort(
            exchange=exchange,
            symbol=symbol,
            collateral=collateral,
            borrowed=borrowed,
            time=time,
            fills=[Fill(
                price=price, size=borrowed, quote=quote, fee=fee, fee_asset=quote_asset
            )],
        )
        if log:
            _log.info(f'{symbol} simulated short position opened at {strftimestamp(time)}')
        return open_position

    def close_simulated_short_position(
        self, position: Position.OpenShort, time: Timestamp, price: Decimal,
        reason: CloseReason, log: bool = True
    ) -> Position.Short:
        base_asset, _ = unpack_symbol(position.symbol)
        fees, filters = self.informant.get_fees_filters(position.exchange, position.symbol)
        borrow_info = self.informant.get_borrow_info(
            exchange=position.exchange, asset=base_asset, account=position.symbol
        )

        interest = _calculate_interest(
            borrowed=position.borrowed,
            hourly_rate=borrow_info.hourly_interest_rate,
            start=position.time,
            end=time,
        )
        size = position.borrowed + interest
        quote = round_down(price * size, filters.quote_precision)
        fee = round_half_up(size * fees.taker, filters.base_precision)
        size += fee

        closed_position = position.close(
            time=time,
            interest=interest,
            fills=[Fill(
                price=price, size=size, quote=quote, fee=fee, fee_asset=base_asset
            )],
            reason=reason,
        )
        if log:
            _log.info(
                f'{closed_position.symbol} simulated short position closed at '
                f'{strftimestamp(time)} due to {reason.name}'
            )
        return closed_position


class PositionMixin(ABC):
    @property
    @abstractmethod
    def informant(self) -> Informant:
        pass

    @property
    @abstractmethod
    def chandler(self) -> Chandler:
        pass

    @property
    @abstractmethod
    def broker(self) -> Broker:
        pass

    @property
    @abstractmethod
    def user(self) -> User:
        pass

    async def open_long_position(
        self, exchange: str, symbol: str, quote: Decimal, mode: TradingMode
    ) -> Position.OpenLong:
        assert mode in [TradingMode.PAPER, TradingMode.LIVE]
        _log.info(f'opening {symbol} {mode.name} long position with {quote} quote')

        res = await self.broker.buy(
            exchange=exchange,
            symbol=symbol,
            quote=quote,
            account='spot',
            test=mode is TradingMode.PAPER,
        )

        open_position = Position.OpenLong(
            exchange=exchange,
            symbol=symbol,
            time=res.time,
            fills=res.fills,
        )
        _log.info(f'{open_position.symbol} {mode.name} long position opened')
        _log.debug(extract_public(open_position))
        return open_position

    async def close_long_position(
        self, position: Position.OpenLong, mode: TradingMode, reason: CloseReason
    ) -> Position.Long:
        assert mode in [TradingMode.PAPER, TradingMode.LIVE]
        _log.info(f'closing {position.symbol} {mode.name} long position')

        res = await self.broker.sell(
            exchange=position.exchange,
            symbol=position.symbol,
            size=position.base_gain,
            account='spot',
            test=mode is TradingMode.PAPER,
        )

        closed_position = position.close(
            time=res.time,
            fills=res.fills,
            reason=reason,
        )
        _log.info(f'{closed_position.symbol} {mode.name} long position closed')
        _log.debug(extract_public(closed_position))
        return closed_position

    async def open_short_position(
        self, exchange: str, symbol: str, collateral: Decimal, mode: TradingMode
    ) -> Position.OpenShort:
        assert mode in [TradingMode.PAPER, TradingMode.LIVE]
        _log.info(f'opening {symbol} {mode.name} short position with {collateral} collateral')

        base_asset, quote_asset = unpack_symbol(symbol)
        _, filters = self.informant.get_fees_filters(exchange, symbol)
        # TODO: We could get a maximum margin multiplier from the exchange and use that but use the
        # lowers multiplier for now for reduced risk.
        margin_multiplier = 2
        # margin_multiplier = self.informant.get_margin_multiplier(exchange)

        price = (await self.chandler.get_last_candle(exchange, symbol, MIN_MS)).close

        if mode is TradingMode.PAPER:
            limit = self.informant.get_borrow_info(
                exchange=exchange, asset=base_asset, account=symbol
            ).limit
            borrowed = _calculate_borrowed(filters, margin_multiplier, limit, collateral, price)
        else:
            _log.info(f'transferring {collateral} {quote_asset} from spot to {symbol} account')
            async with self.user.sync_wallet(exchange=exchange, account=symbol) as wallet:
                await self.user.transfer(
                    exchange=exchange,
                    asset=quote_asset,
                    size=collateral,
                    from_account='spot',
                    to_account=symbol,
                )
                await wallet.updated.wait()

            limit = await self.user.get_max_borrowable(
                exchange=exchange, asset=base_asset, account=symbol
            )
            borrowed = _calculate_borrowed(filters, margin_multiplier, limit, collateral, price)
            _log.info(f'borrowing {borrowed} {base_asset} from {exchange}')
            await self.user.borrow(
                exchange=exchange,
                asset=base_asset,
                size=borrowed,
                account=symbol,
            )

        res = await self.broker.sell(
            exchange=exchange,
            symbol=symbol,
            size=borrowed,
            account=symbol if mode is TradingMode.LIVE else 'spot',
            test=mode is TradingMode.PAPER,
        )

        open_position = Position.OpenShort(
            exchange=exchange,
            symbol=symbol,
            collateral=collateral,
            borrowed=borrowed,
            time=res.time,
            fills=res.fills,
        )
        _log.info(f'{open_position.symbol} {mode.name} short position opened')
        _log.debug(extract_public(open_position))
        return open_position

    async def close_short_position(
        self, position: Position.OpenShort, mode: TradingMode, reason: CloseReason
    ) -> Position.Short:
        assert mode in [TradingMode.PAPER, TradingMode.LIVE]
        _log.info(f'closing {position.symbol} {mode.name} short position')

        base_asset, quote_asset = unpack_symbol(position.symbol)
        fees, filters = self.informant.get_fees_filters(position.exchange, position.symbol)

        # TODO: Take interest from wallet (if Binance supports streaming it for margin account)
        if mode is TradingMode.PAPER:
            borrow_info = self.informant.get_borrow_info(
                exchange=position.exchange, asset=base_asset, account=position.symbol
            )
            interest = _calculate_interest(
                borrowed=position.borrowed,
                hourly_rate=borrow_info.hourly_interest_rate,
                start=position.time,
                end=time_ms(),
            )
        else:
            interest = (await self.user.get_balance(
                exchange=position.exchange,
                account=position.symbol,
                asset=base_asset,
            )).interest

        # Add an extra interest tick in case it is about the get ticked.
        interest_per_tick = borrow_info.hourly_interest_rate * position.borrowed
        size = position.borrowed + interest + interest_per_tick

        res = await self.broker.buy(
            exchange=position.exchange,
            symbol=position.symbol,
            size=size,
            account=position.symbol if mode is TradingMode.LIVE else 'spot',
            test=mode is TradingMode.PAPER,
            ensure_size=True,
        )
        closed_position = position.close(
            interest=interest,
            time=res.time,
            fills=res.fills,
            reason=reason,
        )
        if mode is TradingMode.LIVE:
            _log.info(
                f'repaying {position.borrowed} + {interest} {base_asset} to {position.exchange}'
            )
            await self.user.repay(
                exchange=position.exchange,
                asset=base_asset,
                size=position.borrowed + interest,
                account=position.symbol,
            )

            # It can be that there was an interest tick right before repaying. This means there may
            # still be borrowed funds on the account. Double check and repay more if that is the
            # case.
            # Careful with this check! We may have another position still open.
            new_balance = await self.user.get_balance(
                exchange=position.exchange,
                account=position.symbol,
                asset=base_asset,
            )
            if new_balance.repay > 0:
                _log.warning(
                    f'did not repay enough; still {new_balance.repay} {base_asset} to be repaid'
                )
                if new_balance.available >= new_balance.repay:
                    _log.info(
                        f'can repay {new_balance.repay} {base_asset} without requiring more funds'
                    )
                else:
                    # TODO: Implement
                    _log.error(
                        f'need to buy more {base_asset} to repay {new_balance.repay} but not '
                        'implemented'
                    )
                    raise Exception(f'Did not repay enough {base_asset}; balance {new_balance}')
                await self.user.repay(
                    exchange=position.exchange,
                    asset=base_asset,
                    size=new_balance.repay,
                    account=position.symbol,
                )
                assert (await self.user.get_balance(
                    exchange=position.exchange,
                    account=position.symbol,
                    asset=base_asset,
                )).repay == 0

            transfer = closed_position.collateral + closed_position.profit
            _log.info(
                f'transferring {transfer} {quote_asset} from {position.symbol} to spot account'
            )
            await self.user.transfer(
                exchange=position.exchange,
                asset=quote_asset,
                size=transfer,
                from_account=position.symbol,
                to_account='spot',
            )
            # TODO: Also transfer base asset dust back?

        _log.info(f'{closed_position.symbol} {mode.name} short position closed')
        _log.debug(extract_public(closed_position))
        return closed_position


def _calculate_borrowed(
    filters: Filters, margin_multiplier: int, limit: Decimal, collateral: Decimal, price: Decimal
) -> Decimal:
    collateral_size = filters.size.round_down(collateral / price)
    if collateral_size == 0:
        raise OrderException('Collateral base size 0')
    borrowed = collateral_size * (margin_multiplier - 1)
    if borrowed == 0:
        raise OrderException('Borrowed 0; incorrect margin multiplier?')
    return min(borrowed, limit)


def _calculate_interest(borrowed: Decimal, hourly_rate: Decimal, start: int, end: int) -> Decimal:
    duration = ceil_multiple(end - start, HOUR_MS) // HOUR_MS
    return borrowed * duration * hourly_rate


class StartMixin(ABC):
    @property
    @abstractmethod
    def chandler(self) -> Chandler:
        pass

    async def request_start(
        self, start: Optional[Timestamp], exchange: str, symbols: Iterable[str],
        intervals: Iterable[int]
    ):
        if start is not None:
            if start < 0:
                raise ValueError('Start cannot be negative')
            return start

        first_candles = await asyncio.gather(
            *(self.chandler.get_first_candle(exchange, s, i)
              for s, i in itertools.product(symbols, intervals))
        )
        latest_first_time = max(first_candles, key=lambda c: c.time).time
        _log.info(f'start not specified; start set to {strftimestamp(latest_first_time)}')
        return latest_first_time
