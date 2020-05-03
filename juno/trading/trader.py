import importlib
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Generic, List, NamedTuple, Optional, TypeVar

from juno import Advice, Candle, Fill, Filters, Interval, OrderException, Timestamp, strategies
from juno.brokers import Broker
from juno.components import Chandler, Event, Informant
from juno.exchanges import Exchange
from juno.math import ceil_multiple, round_down, round_half_up
from juno.modules import get_module_type
from juno.strategies import Changed, Strategy
from juno.time import HOUR_MS
from juno.utils import tonamedtuple, unpack_symbol

from .common import (
    LongPosition, MissedCandlePolicy, OpenLongPosition, OpenShortPosition, ShortPosition,
    TradingSummary
)

_log = logging.getLogger(__name__)

TStrategy = TypeVar('TStrategy', bound=Strategy)


class Trader:
    @dataclass
    class State(Generic[TStrategy]):
        strategy: Optional[TStrategy] = None
        changed: Optional[Changed] = None
        quote: Decimal = Decimal('-1.0')
        summary: Optional[TradingSummary] = None
        open_long_position: Optional[OpenLongPosition] = None
        open_short_position: Optional[OpenShortPosition] = None
        first_candle: Optional[Candle] = None
        last_candle: Optional[Candle] = None
        highest_close_since_position = Decimal('0.0')
        lowest_close_since_position = Decimal('Inf')
        current: Timestamp = 0
        start_adjusted: bool = False

    class Config(NamedTuple):
        exchange: str
        symbol: str
        interval: Interval
        start: Timestamp
        end: Timestamp
        quote: Decimal
        strategy: str
        strategy_module: str = strategies.__name__
        trailing_stop: Decimal = Decimal('0.0')  # 0 means disabled.
        test: bool = True  # No effect if broker is None.
        strategy_args: List[Any] = []
        strategy_kwargs: Dict[str, Any] = {}
        channel: str = 'default'
        missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE
        adjust_start: bool = False
        long: bool = True  # Take long positions.
        short: bool = False  # Also take short positions.

        @property
        def base_asset(self) -> str:
            return unpack_symbol(self.symbol)[0]

        @property
        def quote_asset(self) -> str:
            return unpack_symbol(self.symbol)[1]

        @property
        def upside_trailing_factor(self) -> Decimal:
            return 1 - self.trailing_stop

        @property
        def downside_trailing_factor(self) -> Decimal:
            return 1 + self.trailing_stop

        def new_strategy(self) -> Strategy:
            return get_module_type(importlib.import_module(self.strategy_module), self.strategy)(
                *self.strategy_args, **self.strategy_kwargs
            )

    def __init__(
        self,
        chandler: Chandler,
        informant: Informant,
        broker: Optional[Broker] = None,
        event: Event = Event(),
        exchanges: List[Exchange] = [],
    ) -> None:
        self._chandler = chandler
        self._informant = informant
        self._broker = broker
        self._event = event
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}

    @property
    def has_broker(self) -> bool:
        return self._broker is not None

    async def run(self, config: Config, state: Optional[State] = None) -> TradingSummary:
        assert config.start >= 0
        assert config.end > 0
        assert config.end > config.start
        assert 0 <= config.trailing_stop < 1
        if config.short:
            assert self._informant.get_borrow_info(config.exchange, config.quote_asset)
            assert self._informant.get_fees_filters(
                config.exchange, config.symbol
            )[1].is_margin_trading_allowed

        state = state or Trader.State()

        if state.quote == -1:
            state.quote = config.quote

        if not state.summary:
            state.summary = TradingSummary(
                start=config.start,
                quote=config.quote,
                quote_asset=config.quote_asset,
            )

        if not state.strategy:
            state.strategy = config.new_strategy()

        if not state.changed:
            state.changed = Changed(True)

        if not state.current:
            state.current = config.start

        if config.adjust_start and not state.start_adjusted:
            # Adjust start to accommodate for the required history before a strategy
            # becomes effective. Only do it on first run because subsequent runs mean
            # missed candles and we don't want to fetch passed a missed candle.
            _log.info(
                f'fetching {state.strategy.adjust_hint} candle(s) before start time to warm-up '
                'strategy'
            )
            state.current -= state.strategy.adjust_hint * config.interval
            state.start_adjusted = True

        try:
            while True:
                restart = False

                async for candle in self._chandler.stream_candles(
                    exchange=config.exchange,
                    symbol=config.symbol,
                    interval=config.interval,
                    start=state.current,
                    end=config.end,
                ):
                    # Check if we have missed a candle.
                    if (
                        state.last_candle
                        and candle.time - state.last_candle.time >= config.interval * 2
                    ):
                        # TODO: walrus operator
                        num_missed = (candle.time - state.last_candle.time) // config.interval - 1
                        if config.missed_candle_policy is MissedCandlePolicy.RESTART:
                            _log.info('restarting strategy due to missed candle(s)')
                            restart = True
                            state.strategy = config.new_strategy()
                            state.current = candle.time + config.interval
                        elif config.missed_candle_policy is MissedCandlePolicy.LAST:
                            _log.info(f'filling {num_missed} missed candles with last values')
                            last_candle = state.last_candle
                            for i in range(1, num_missed + 1):
                                missed_candle = Candle(
                                    time=last_candle.time + i * config.interval,
                                    open=last_candle.open,
                                    high=last_candle.high,
                                    low=last_candle.low,
                                    close=last_candle.close,
                                    volume=last_candle.volume,
                                    closed=last_candle.closed,
                                )
                                await self._tick(config, state, missed_candle)

                    await self._tick(config, state, candle)

                    if restart:
                        break

                if not restart:
                    break
        finally:
            if state.last_candle:
                if state.open_long_position:
                    _log.info('ending trading but long position open; closing')
                    await self._close_long_position(config, state, state.last_candle)
                if state.open_short_position:
                    _log.info('ending trading but short position open; closing')
                    await self._close_short_position(config, state, state.last_candle)

                state.summary.finish(state.last_candle.time + config.interval)
            else:
                state.summary.finish(config.start)

        return state.summary

    async def _tick(self, config: Config, state: State, candle: Candle) -> None:
        await self._event.emit(config.channel, 'candle', candle)

        assert state.strategy
        assert state.changed
        assert state.summary
        advice = state.changed.update(state.strategy.update(candle))
        _log.debug(f'received advice: {advice.name}')
        # Make sure strategy doesn't give advice during "adjusted start" period.
        if state.current < state.summary.start:
            assert advice is Advice.NONE

        if state.open_long_position:
            if advice in [Advice.SHORT, Advice.LIQUIDATE]:
                await self._close_long_position(config, state, candle)
            elif config.trailing_stop:
                state.highest_close_since_position = max(
                    state.highest_close_since_position, candle.close
                )
                target = state.highest_close_since_position * config.upside_trailing_factor
                if candle.close <= target:
                    _log.info(f'upside trailing stop hit at {config.trailing_stop}; selling')
                    await self._close_long_position(config, state, candle)
                    assert advice is not Advice.LONG
        elif state.open_short_position:
            if advice in [Advice.LONG, Advice.LIQUIDATE]:
                await self._close_short_position(config, state, candle)
            elif config.trailing_stop:
                state.lowest_close_since_position = min(
                    state.lowest_close_since_position, candle.close
                )
                target = state.lowest_close_since_position * config.downside_trailing_factor
                if candle.close >= target:
                    _log.info(f'downside trailing stop hit at {config.trailing_stop}; selling')
                    await self._close_short_position(config, state, candle)
                    assert advice is not Advice.SHORT

        if not state.open_long_position and not state.open_short_position:
            if config.long and advice is Advice.LONG:
                await self._open_long_position(config, state, candle)
                state.highest_close_since_position = candle.close
            elif config.short and advice is Advice.SHORT:
                await self._open_short_position(config, state, candle)
                state.lowest_close_since_position = candle.close

        if not state.first_candle:
            _log.info(f'first candle {candle}')
            state.first_candle = candle
        state.last_candle = candle
        state.current = candle.time + config.interval

    async def _open_long_position(self, config: Config, state: State, candle: Candle) -> None:
        assert not state.open_long_position
        assert not state.open_short_position

        position = (
            await open_long_position(
                broker=self._broker,
                candle=candle,
                exchange=config.exchange,
                symbol=config.symbol,
                test=config.test,
                quote=state.quote,
            ) if self._broker else open_simulated_long_position(
                informant=self._informant,
                candle=candle,
                exchange=config.exchange,
                symbol=config.symbol,
                quote=state.quote,
            )
        )

        state.quote -= Fill.total_quote(position.fills)
        state.open_long_position = position

        _log.info(f'long position opened: {candle}')
        _log.debug(tonamedtuple(state.open_long_position))
        await self._event.emit(
            config.channel, 'position_opened', state.open_long_position, state.summary
        )

    async def _close_long_position(self, config: Config, state: State, candle: Candle) -> None:
        assert state.summary
        assert state.open_long_position

        position = (
            await close_long_position(
                broker=self._broker,
                candle=candle,
                exchange=config.exchange,
                symbol=config.symbol,
                test=config.test,
                position=state.open_long_position,
            ) if self._broker else close_simulated_long_position(
                informant=self._informant,
                candle=candle,
                exchange=config.exchange,
                symbol=config.symbol,
                position=state.open_long_position,
            )
        )

        state.quote += (
            Fill.total_quote(position.close_fills) - Fill.total_fee(position.close_fills)
        )
        state.open_long_position = None
        state.summary.append_position(position)

        _log.info(f'long position closed: {candle}')
        _log.debug(tonamedtuple(position))
        await self._event.emit(config.channel, 'position_closed', position, state.summary)

    async def _open_short_position(self, config: Config, state: State, candle: Candle) -> None:
        assert not state.open_long_position
        assert not state.open_short_position

        position = (
            await open_short_position(
                informant=self._informant,
                broker=self._broker,
                exchange=self._exchanges[config.exchange],
                candle=candle,
                symbol=config.symbol,
                test=config.test,
                collateral=state.quote,
            ) if self._broker else open_simulated_short_position(
                informant=self._informant,
                candle=candle,
                exchange=config.exchange,
                symbol=config.symbol,
                collateral=state.quote,
            )
        )

        state.quote += Fill.total_quote(position.fills) - Fill.total_fee(position.fills)
        state.open_short_position = position

        _log.info(f'short position opened: {candle}')
        _log.debug(tonamedtuple(state.open_short_position))
        await self._event.emit(
            config.channel, 'position_opened', state.open_short_position, state.summary
        )

    async def _close_short_position(self, config: Config, state: State, candle: Candle) -> None:
        assert state.summary
        assert state.open_short_position

        position = (
            await close_short_position(
                informant=self._informant,
                broker=self._broker,
                exchange=self._exchanges[config.exchange],
                candle=candle,
                symbol=config.symbol,
                test=config.test,
                position=state.open_short_position,
            ) if self._broker else close_simulated_short_position(
                informant=self._informant,
                candle=candle,
                exchange=config.exchange,
                symbol=config.symbol,
                position=state.open_short_position,
            )
        )

        state.quote -= Fill.total_quote(position.close_fills)
        state.open_short_position = None
        state.summary.append_position(position)

        _log.info(f'short position closed: {candle}')
        _log.debug(tonamedtuple(position))
        await self._event.emit(config.channel, 'position_closed', position, state.summary)


def open_simulated_long_position(
    informant: Informant, candle: Candle, exchange: str, symbol: str, quote: Decimal
) -> OpenLongPosition:
    price = candle.close
    fees, filters = informant.get_fees_filters(exchange, symbol)

    size = filters.size.round_down(quote / price)
    if size == 0:
        raise OrderException()

    quote = round_down(price * size, filters.quote_precision)
    fee = round_half_up(size * fees.taker, filters.base_precision)

    base_asset, _ = unpack_symbol(symbol)
    return OpenLongPosition(
        symbol=symbol,
        time=candle.time,
        fills=[Fill(
            price=price, size=size, quote=quote, fee=fee, fee_asset=base_asset
        )],
    )


async def open_long_position(
    broker: Broker, candle: Candle, exchange: str, symbol: str, quote: Decimal, test: bool
) -> OpenLongPosition:
    res = await broker.buy_by_quote(
        exchange=exchange,
        symbol=symbol,
        quote=quote,
        test=test,
    )
    return OpenLongPosition(
        symbol=symbol,
        time=candle.time,
        fills=res.fills,
    )


def close_simulated_long_position(
    informant: Informant, candle: Candle, position: OpenLongPosition, exchange: str, symbol: str
) -> LongPosition:
    price = candle.close
    _, quote_asset = unpack_symbol(symbol)
    fees, filters = informant.get_fees_filters(exchange, symbol)
    size = filters.size.round_down(position.base_gain)
    quote = round_down(price * size, filters.quote_precision)
    fee = round_half_up(quote * fees.taker, filters.quote_precision)
    return position.close(
        time=candle.time,
        fills=[Fill(
            price=price, size=size, quote=quote, fee=fee, fee_asset=quote_asset
        )],
    )


async def close_long_position(
    broker: Broker, candle: Candle, position: OpenLongPosition, exchange: str, symbol: str,
    test: bool
) -> LongPosition:
    res = await broker.sell(
        exchange=exchange,
        symbol=symbol,
        size=position.base_gain,
        test=test,
    )
    return position.close(
        time=candle.time,
        fills=res.fills,
    )


def open_simulated_short_position(
    informant: Informant, candle: Candle, exchange: str, symbol: str, collateral: Decimal
) -> OpenShortPosition:
    fees, filters = informant.get_fees_filters(exchange, symbol)
    margin_multiplier = informant.get_margin_multiplier(exchange)
    price = candle.close
    borrowed = _calculate_borrowed(filters, margin_multiplier, collateral, price)
    quote = round_down(price * borrowed, filters.quote_precision)
    fee = round_half_up(quote * fees.taker, filters.quote_precision)
    _, quote_asset = unpack_symbol(symbol)
    return OpenShortPosition(
        symbol=symbol,
        collateral=collateral,
        borrowed=borrowed,
        time=candle.time,
        fills=[Fill(
            price=price, size=borrowed, quote=quote, fee=fee, fee_asset=quote_asset
        )],
    )


async def open_short_position(
    informant: Informant, broker: Broker, exchange: Exchange, candle: Candle, symbol: str,
    collateral: Decimal, test: bool
) -> OpenShortPosition:
    base_asset, quote_asset = unpack_symbol(symbol)
    exchange_name = type(exchange).__name__.lower()
    _, filters = informant.get_fees_filters(exchange_name, symbol)
    margin_multipler = informant.get_margin_multiplier(exchange_name)
    price = candle.close

    borrowed = (
        _calculate_borrowed(filters, margin_multipler, collateral, price)
        if test
        else await exchange.get_max_borrowable(quote_asset)
    )

    if not test:
        _log.info(f'transferring {collateral} {quote_asset} to margin account')
        await exchange.transfer(quote_asset, collateral, margin=True)
        _log.info(f'borrowing {borrowed} {base_asset} from exchange')
        await exchange.borrow(asset=base_asset, size=borrowed)

    res = await broker.sell(
        exchange=exchange_name,
        symbol=symbol,
        size=borrowed,
        test=test,
        margin=not test,
    )
    return OpenShortPosition(
        symbol=symbol,
        collateral=collateral,
        borrowed=borrowed,
        time=candle.time,
        fills=res.fills,
    )


def close_simulated_short_position(
    informant: Informant, candle: Candle, position: OpenShortPosition, exchange: str, symbol: str
) -> ShortPosition:
    price = candle.close
    base_asset, _ = unpack_symbol(symbol)
    fees, filters = informant.get_fees_filters(exchange, symbol)
    borrow_info = informant.get_borrow_info(exchange, base_asset)

    interest = _calculate_interest(
        borrow_info.hourly_interest_rate,
        position.time,
        candle.time,
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


async def close_short_position(
    informant: Informant, broker: Broker, exchange: Exchange, candle: Candle,
    position: OpenShortPosition, symbol: str, test: bool
) -> ShortPosition:
    base_asset, quote_asset = unpack_symbol(symbol)
    exchange_name = type(exchange).__name__.lower()
    fees, filters = informant.get_fees_filters(exchange_name, symbol)
    borrow_info = informant.get_borrow_info(exchange_name, symbol)

    interest = (
        _calculate_interest(borrow_info.hourly_interest_rate, position.time, candle.time)
        if test
        else (await exchange.map_balances(margin=True))[base_asset].interest
    )
    size = position.borrowed + interest
    fee = round_half_up(size * fees.taker, filters.base_precision)
    size = filters.size.round_up(size + fee)

    res = await broker.buy(
        exchange=exchange_name,
        symbol=symbol,
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
        await exchange.repay(base_asset, position.borrowed + interest)
        # Validate!
        # TODO: Remove if known to work or pay extra if needed.
        new_balance = (await exchange.map_balances(margin=True))[base_asset]
        if new_balance.repay != 0:
            _log.error(f'did not repay enough; balance {new_balance}')
            assert new_balance.repay == 0

        transfer = closed_position.collateral + closed_position.profit
        _log.info(f'transferring {transfer} {quote_asset} to spot account')
        await exchange.transfer(quote_asset, transfer, margin=False)

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


def _calculate_interest(hourly_rate: Decimal, start: int, end: int) -> Decimal:
    duration = ceil_multiple(end - start, HOUR_MS) // HOUR_MS
    return duration * hourly_rate
