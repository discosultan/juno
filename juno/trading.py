from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import IntEnum
from types import ModuleType
from typing import Iterable, Optional, Sequence, Union

from tenacity import (
    RetryError, before_sleep_log, retry, retry_if_exception_type, stop_after_attempt,
    wait_exponential
)

from juno import BadOrder, Balance, Fill, Filters, Interval, Timestamp
from juno.asyncio import gather_dict
from juno.brokers import Broker
from juno.components import Chandler, Informant, User
from juno.math import annualized, ceil_multiple, floor_multiple_offset, round_down, round_half_up
from juno.time import HOUR_MS, MIN_MS, strftimestamp, time_ms
from juno.utils import extract_public, unpack_assets, unpack_base_asset, unpack_quote_asset

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


class _UnexpectedExchangeResult(Exception):
    pass


class PositionNotOpen(Exception):
    pass


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

        def quote_delta(self) -> Decimal:
            return self.gain

        @property
        def cost(self) -> Decimal:
            return Fill.total_quote(self.open_fills)

        @property
        def base_gain(self) -> Decimal:
            return (
                Fill.total_size(self.open_fills)
                - Fill.total_fee(self.open_fills, unpack_base_asset(self.symbol))
            )

        @property
        def base_cost(self) -> Decimal:
            return Fill.total_size(self.close_fills)

        @property
        def gain(self) -> Decimal:
            return (
                Fill.total_quote(self.close_fills)
                - Fill.total_fee(self.close_fills, unpack_quote_asset(self.symbol))
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

        def close(
            self, time: Timestamp, fills: list[Fill], reason: CloseReason
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
            return (
                Fill.total_size(self.fills)
                - Fill.total_fee(self.fills, unpack_base_asset(self.symbol))
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
            return max(self.profit / self.cost, Decimal('-1.0'))

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
            self, interest: Decimal, time: Timestamp, fills: list[Fill],
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
            return (
                Fill.total_quote(self.fills)
                - Fill.total_fee(self.fills, unpack_quote_asset(self.symbol))
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

    positions: list[Position.Closed] = field(default_factory=list)

    end: Timestamp = -1

    def __post_init__(self):
        if self.end == -1:
            self.end = self.start

    @property
    def profit(self) -> Decimal:
        return sum((p.profit for p in self.positions), Decimal('0.0'))

    def append_position(self, pos: Position.Closed) -> None:
        self.positions.append(pos)
        self.finish(pos.close_time)

    def get_positions(
        self,
        type_: Optional[type[Position.Closed]] = None,
        reason: Optional[CloseReason] = None,
    ) -> Iterable[Position.Closed]:
        result = (p for p in self.positions)
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


class SimulatedPositionMixin(ABC):
    @property
    @abstractmethod
    def informant(self) -> Informant:
        pass

    def open_simulated_long_position(
        self, exchange: str, symbol: str, time: Timestamp, price: Decimal, quote: Decimal,
        log: bool = True
    ) -> Position.OpenLong:
        base_asset, _ = unpack_assets(symbol)
        fees, filters = self.informant.get_fees_filters(exchange, symbol)

        size = filters.size.round_down(quote / price)
        if size == 0:
            raise BadOrder()
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
        _, quote_asset = unpack_assets(position.symbol)
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
        base_asset, quote_asset = unpack_assets(symbol)
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
        base_asset, _ = unpack_assets(position.symbol)
        fees, filters = self.informant.get_fees_filters(position.exchange, position.symbol)
        asset_info = self.informant.get_asset_info(exchange=position.exchange, asset=base_asset)
        borrow_info = self.informant.get_borrow_info(
            exchange=position.exchange, asset=base_asset, account=position.symbol
        )

        interest = _calculate_interest(
            borrowed=position.borrowed,
            hourly_rate=borrow_info.hourly_interest_rate,
            start=position.time,
            end=time,
            precision=asset_info.precision,
        )
        size = position.borrowed + interest
        fee = round_half_up(size * fees.taker, filters.base_precision)
        size += fee
        quote = round_down(price * size, filters.quote_precision)

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
        _log.info(f'opening position {symbol} {mode.name} long with {quote} quote')

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
        _log.info(f'opened position {open_position.symbol} {mode.name} long')
        _log.debug(extract_public(open_position))
        return open_position

    async def close_long_position(
        self, position: Position.OpenLong, mode: TradingMode, reason: CloseReason
    ) -> Position.Long:
        assert mode in [TradingMode.PAPER, TradingMode.LIVE]
        _log.info(f'closing position {position.symbol} {mode.name} long')

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
        _log.info(f'closed position {closed_position.symbol} {mode.name} long')
        _log.debug(extract_public(closed_position))
        return closed_position

    async def open_short_position(
        self, exchange: str, symbol: str, collateral: Decimal, mode: TradingMode
    ) -> Position.OpenShort:
        assert mode in [TradingMode.PAPER, TradingMode.LIVE]
        _log.info(f'opening position {symbol} {mode.name} short with {collateral} collateral')

        base_asset, quote_asset = unpack_assets(symbol)
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
            await self.user.transfer(
                exchange=exchange,
                asset=quote_asset,
                size=collateral,
                from_account='spot',
                to_account=symbol,
            )

            # Looks like Binance caches the result, so even with retries, it can be that it will
            # keep returning 0 while we have sufficient collateral present. To circumvent, once
            # we hit the retry limit, we will try one more time. But this time, by first borrowing
            # QUOTE, instead of base asset. This seems to reset the cache.
            try:
                borrowable = await self._get_max_borrowable_with_retries(
                    exchange=exchange, account=symbol, asset=base_asset
                )
            except RetryError:
                _log.warning(
                    'borrowable 0 even after retries; trying once more by first getting quote '
                    'asset max borrowable; hopefully this solves any caching issue on the exchange'
                )
                await self.user.get_max_borrowable(
                    exchange=exchange, account=symbol, asset=quote_asset
                )
                borrowable = await self._get_max_borrowable_with_retries(
                    exchange=exchange, account=symbol, asset=base_asset
                )

            borrowed = _calculate_borrowed(
                filters, margin_multiplier, borrowable, collateral, price
            )
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
        _log.info(f'opened position {open_position.symbol} {mode.name} short')
        _log.debug(extract_public(open_position))
        return open_position

    # Even when waiting for wallet update, Binance can still return 0 as borrow amount for base
    # asset. We retry a couple of times as we have nothing else to await on.
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(),
        retry=retry_if_exception_type(_UnexpectedExchangeResult),
        before_sleep=before_sleep_log(_log, logging.WARNING)
    )
    async def _get_max_borrowable_with_retries(
        self, exchange: str, account: str, asset: str
    ) -> Decimal:
        borrowable = await self.user.get_max_borrowable(
            exchange=exchange, account=account, asset=asset
        )
        if borrowable == 0:
            raise _UnexpectedExchangeResult(
                f'Borrowable amount 0 for account {account} asset {asset}'
            )
        return borrowable

    async def close_short_position(
        self, position: Position.OpenShort, mode: TradingMode, reason: CloseReason
    ) -> Position.Short:
        assert mode in [TradingMode.PAPER, TradingMode.LIVE]
        _log.info(f'closing position {position.symbol} {mode.name} short')

        base_asset, quote_asset = unpack_assets(position.symbol)
        asset_info = self.informant.get_asset_info(exchange=position.exchange, asset=base_asset)
        borrow_info = self.informant.get_borrow_info(
            exchange=position.exchange, asset=base_asset, account=position.symbol
        )

        # TODO: Take interest from wallet (if Binance supports streaming it for margin account)
        if mode is TradingMode.PAPER:
            interest = _calculate_interest(
                borrowed=position.borrowed,
                hourly_rate=borrow_info.hourly_interest_rate,
                start=position.time,
                end=time_ms(),
                precision=asset_info.precision,
            )
        else:
            interest = (await self.user.get_balance(
                exchange=position.exchange,
                account=position.symbol,
                asset=base_asset,
            )).interest

        # Add an extra interest tick in case it is about to get ticked.
        interest_per_tick = borrow_info.hourly_interest_rate * position.borrowed
        repay = position.borrowed + interest
        size = repay + interest_per_tick

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
                size=repay,
                account=position.symbol,
            )

            # It can be that there was an interest tick right before repaying. This means there may
            # still be borrowed funds on the account. Double check and repay more if that is the
            # case.
            # Careful with this check! We may have another position still open.
            new_balance = await self._get_repaid_balance_with_retries(
                exchange=position.exchange,
                account=position.symbol,
                asset=base_asset,
                original_borrowed=position.borrowed,
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
                new_balance = await self.user.get_balance(
                    exchange=position.exchange,
                    account=position.symbol,
                    asset=base_asset,
                )
                assert new_balance.repay == 0

            transfer = closed_position.collateral + closed_position.profit
            _log.info(
                f'transferring {transfer} {quote_asset} from {position.symbol} to spot account'
            )
            transfer_tasks = [
                self.user.transfer(
                    exchange=position.exchange,
                    asset=quote_asset,
                    size=transfer,
                    from_account=position.symbol,
                    to_account='spot',
                ),
            ]
            if new_balance.available > 0:
                _log.info(
                    f'transferring {new_balance.available} {base_asset} from {position.symbol} to '
                    'spot account'
                )
                transfer_tasks.append(self.user.transfer(
                    exchange=position.exchange,
                    asset=base_asset,
                    size=new_balance.available,
                    from_account=position.symbol,
                    to_account='spot',
                ))
            await asyncio.gather(*transfer_tasks)

        _log.info(f'closed position {closed_position.symbol} {mode.name} short')
        _log.debug(extract_public(closed_position))
        return closed_position

    # After repaying borrowed asset, Binance can still return the old repay balance. We retry
    # until the balance has changed.
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(),
        retry=retry_if_exception_type(_UnexpectedExchangeResult),
        before_sleep=before_sleep_log(_log, logging.WARNING)
    )
    async def _get_repaid_balance_with_retries(
        self, exchange: str, account: str, asset: str, original_borrowed: Decimal
    ) -> Balance:
        balance = await self.user.get_balance(
            exchange=exchange,
            account=account,
            asset=asset,
        )
        if balance.borrowed == original_borrowed:
            raise _UnexpectedExchangeResult(
                f'Borrowed amount still {original_borrowed} for account {account} asset {asset}'
            )
        return balance


def _calculate_borrowed(
    filters: Filters, margin_multiplier: int, limit: Decimal, collateral: Decimal, price: Decimal
) -> Decimal:
    collateral_size = filters.size.round_down(collateral / price)
    if collateral_size == 0:
        raise BadOrder('Collateral base size 0')
    borrowed = collateral_size * (margin_multiplier - 1)
    if borrowed == 0:
        raise BadOrder('Borrowed 0; incorrect margin multiplier?')
    return min(borrowed, limit)


def _calculate_interest(
    borrowed: Decimal, hourly_rate: Decimal, start: int, end: int, precision: int
) -> Decimal:
    duration = ceil_multiple(end - start, HOUR_MS) // HOUR_MS
    return round_half_up(borrowed * duration * hourly_rate, precision=precision)


class StartMixin(ABC):
    @property
    @abstractmethod
    def chandler(self) -> Chandler:
        pass

    async def request_candle_start(
        self, start: Optional[Timestamp], exchange: str, symbols: Sequence[str],
        interval: int
    ) -> int:
        """Figures out an appropriate candle start time based on the requested start.
           If no specific start is requested, finds the earliest start of the interval where all
           candle intervals are available.
           If start is specified, floors the time to interval if interval is <= DAY_MS, otherwise
           floors to DAY_MS.
        """
        if len(symbols) == 0:
            raise ValueError('Must have at least one symbol for requesting start')
        if start is not None and start < 0:
            raise ValueError('Start cannot be negative')

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
            _log.info(f'start not specified; start set to {strftimestamp(result)}')
        elif result != start:
            _log.info(
                f'start specified as {strftimestamp(start)}; adjusted to {strftimestamp(result)}'
            )
        else:
            _log.info(f'start specified as {strftimestamp(start)}; no adjustment needed')
        return result
