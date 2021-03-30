from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Coroutine, Optional, TypeVar
from uuid import uuid4

from more_itertools import take

from juno import Advice, Candle, Interval, Timestamp
from juno.asyncio import (
    Event, SlotBarrier, cancel, create_task_cancel_owner_on_exception, process_task_on_queue
)
from juno.brokers import Broker
from juno.components import Chandler, Events, Informant, User
from juno.exchanges import Exchange
from juno.math import floor_multiple_offset, rpstdev, split
from juno.stop_loss import Noop as NoopStopLoss
from juno.stop_loss import StopLoss
from juno.strategies import Changed, Signal
from juno.take_profit import Noop as NoopTakeProfit
from juno.take_profit import TakeProfit
from juno.time import strftimestamp, time_ms
from juno.trading import (
    CloseReason, Position, PositionMixin, PositionNotOpen, SimulatedPositionMixin, StartMixin,
    TradingMode, TradingSummary
)
from juno.typing import TypeConstructor

from .trader import Trader

_log = logging.getLogger(__name__)

T = TypeVar('T')

SYMBOL_PATTERN = '*-btc'


@dataclass(frozen=True)
class MultiConfig:
    exchange: str
    interval: Interval
    end: Timestamp
    strategy: TypeConstructor[Signal]
    # Overrides default strategy.
    symbol_strategies: dict[str, TypeConstructor[Signal]] = field(default_factory=dict)
    stop_loss: Optional[TypeConstructor[StopLoss]] = None
    take_profit: Optional[TypeConstructor[TakeProfit]] = None
    start: Optional[Timestamp] = None  # None means max earliest is found.
    quote: Optional[Decimal] = None  # None means exchange wallet is queried.
    trail_stop_loss: bool = True
    adjust_start: bool = True
    mode: TradingMode = TradingMode.BACKTEST
    channel: str = 'default'
    long: bool = True  # Take long positions.
    short: bool = False  # Take short positions.
    close_on_exit: bool = True  # Whether to close open positions on exit.
    track: list[str] = field(default_factory=list)
    track_exclude: list[str] = field(default_factory=list)  # Symbols to ignore.
    track_count: int = 4
    track_required_start: Optional[Timestamp] = None
    position_count: int = 2
    exchange_candle_timeout: Optional[Interval] = None
    allowed_age_drift: int = 0


@dataclass
class MultiState:
    config: MultiConfig
    close_on_exit: bool
    symbol_states: dict[str, _SymbolState]
    quotes: list[Decimal]
    summary: TradingSummary
    start: Timestamp  # Candle time.
    next_: Timestamp  # Candle time.
    real_start: Timestamp
    open_new_positions: bool = True  # Whether new positions can be opened.

    id: str = field(default_factory=lambda: str(uuid4()))
    running: bool = False

    @property
    def open_positions(self) -> list[Position.Open]:
        return [s.open_position for s in self.symbol_states.values() if s.open_position]


@dataclass
class _SymbolState:
    symbol: str
    strategy: Signal
    changed: Changed
    adjusted_start: Timestamp
    start: Timestamp
    next_: Timestamp
    stop_loss: StopLoss
    take_profit: TakeProfit
    open_position: Optional[Position.Open] = None
    allocated_quote: Decimal = Decimal('0.0')
    first_candle: Optional[Candle] = None
    last_candle: Optional[Candle] = None
    advice: Advice = Advice.NONE
    advice_age: int = 0
    reason: CloseReason = CloseReason.STRATEGY

    @property
    def ready(self) -> bool:
        return self.first_candle is not None


class Multi(Trader[MultiConfig, MultiState], PositionMixin, SimulatedPositionMixin, StartMixin):
    @staticmethod
    def config() -> type[MultiConfig]:
        return MultiConfig

    @staticmethod
    def state() -> type[MultiState]:
        return MultiState

    def __init__(
        self,
        chandler: Chandler,
        informant: Informant,
        user: Optional[User] = None,
        broker: Optional[Broker] = None,
        events: Events = Events(),
        exchanges: list[Exchange] = [],
        get_time_ms: Callable[[], int] = time_ms,
    ) -> None:
        self._chandler = chandler
        self._informant = informant
        self._user = user
        self._broker = broker
        self._events = events
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._get_time_ms = get_time_ms
        self._queues: dict[str, asyncio.Queue] = {}  # Key: state id

    @property
    def informant(self) -> Informant:
        return self._informant

    @property
    def broker(self) -> Broker:
        assert self._broker
        return self._broker

    @property
    def chandler(self) -> Chandler:
        return self._chandler

    @property
    def exchanges(self) -> dict[str, Exchange]:
        return self._exchanges

    @property
    def user(self) -> User:
        assert self._user
        return self._user

    async def initialize(self, config: MultiConfig) -> MultiState:
        assert config.mode is TradingMode.BACKTEST or self.broker
        assert config.start is None or config.start >= 0
        assert config.end > 0
        assert config.start is None or config.end > config.start
        assert config.position_count > 0
        assert config.position_count <= config.track_count
        assert len(config.track) <= config.track_count
        assert not list(set(config.track) & set(config.track_exclude))  # No common elements.
        assert config.allowed_age_drift >= 0

        symbols = await self._find_top_symbols(config)

        start = await self.request_candle_start(
            config.start, config.exchange, symbols, config.interval
        )
        real_start = self._get_time_ms()

        quote = await self.request_quote(config.quote, config.exchange, 'btc', config.mode)
        position_quote = quote / config.position_count
        for symbol in symbols:
            _, filters = self._informant.get_fees_filters(config.exchange, symbol)
            assert position_quote > filters.price.min

        return MultiState(
            config=config,
            close_on_exit=config.close_on_exit,
            real_start=real_start,
            start=start,
            next_=start,
            quotes=self._split_quote(quote, config.position_count, config.exchange),
            summary=TradingSummary(
                start=start if config.mode is TradingMode.BACKTEST else real_start,
                quote=quote,
                quote_asset='btc',  # TODO: support others
            ),
            symbol_states={s: self._create_symbol_state(s, start, config) for s in symbols},
        )

    def _split_quote(self, quote: Decimal, parts: int, exchange: str) -> list[Decimal]:
        asset_info = self._informant.get_asset_info(exchange, 'btc')
        return split(quote, parts, asset_info.precision)

    def _create_symbol_state(
        self, symbol: str, start: int, config: MultiConfig
    ) -> _SymbolState:
        strategy = config.symbol_strategies.get(symbol, config.strategy).construct()

        adjusted_start = start
        if config.adjust_start:
            _log.info(
                f'fetching {strategy.maturity - 1} {symbol} candle(s) before start time to '
                'warm-up strategy'
            )
            adjusted_start = max(start - (strategy.maturity - 1) * config.interval, 0)

        return _SymbolState(
            symbol=symbol,
            strategy=strategy,
            changed=Changed(True),
            adjusted_start=adjusted_start,
            start=start,
            next_=adjusted_start,
            stop_loss=(
                NoopStopLoss() if config.stop_loss is None
                else config.stop_loss.construct()
            ),
            take_profit=(
                NoopTakeProfit() if config.take_profit is None
                else config.take_profit.construct()
            ),
        )

    async def run(self, state: MultiState) -> TradingSummary:
        config = state.config
        _log.info(
            f'managing up to {config.position_count} positions by tracking top '
            f'{config.track_count} symbols: {list(state.symbol_states.keys())}'
        )
        _log.info(f'quote split as: {state.quotes}')

        self._queues[state.id] = asyncio.Queue()
        state.running = True
        try:
            track_tasks: dict[str, asyncio.Task] = {}
            await self._manage_positions(state, track_tasks)
        finally:
            state.running = False
            # Remove queue and wait for any pending position tasks to finish.
            queue = self._queues.pop(state.id)
            await queue.join()

            await cancel(*track_tasks.values())
            if state.close_on_exit:
                await self._close_positions(
                    state,
                    [ss for ss in state.symbol_states.values() if ss.open_position],
                    CloseReason.CANCELLED,
                )
            if config.end is not None and config.end <= state.real_start:  # Backtest.
                end = (
                    max(
                        s.last_candle.time for s in state.symbol_states.values() if s.last_candle
                    ) + config.interval
                    if any(s.last_candle for s in state.symbol_states.values())
                    else state.summary.start + config.interval
                )
            else:  # Paper or live.
                end = min(self._get_time_ms(), config.end)
            state.summary.finish(end)

        _log.info('finished')
        return state.summary

    async def _find_top_symbols(self, config: MultiConfig) -> list[str]:
        tickers = self._informant.map_tickers(
            config.exchange, symbol_patterns=[SYMBOL_PATTERN],
            exclude_symbol_patterns=config.track_exclude, spot=True, isolated_margin=True
        )
        # Filter.
        if config.track_required_start is not None:
            first_candles = await asyncio.gather(
                *(
                    self._chandler.get_first_candle(config.exchange, s, config.interval)
                    for s in tickers.keys()
                )
            )
            tickers = {
                s: t for (s, t), c in zip(tickers.items(), first_candles)
                if c.time <= config.track_required_start
            }
        # Validate.
        if len(tickers) < config.track_count:
            required_start_msg = (
                '' if config.track_required_start is None
                else f' with required start at {strftimestamp(config.track_required_start)}'
            )
            raise ValueError(
                f'Exchange only supports {len(tickers)} symbols matching pattern {SYMBOL_PATTERN} '
                f'while {config.track_count} requested{required_start_msg}'
            )
        # Compose.
        count = config.track_count - len(config.track)
        return config.track + [s for s, t in take(count, tickers.items()) if t not in config.track]

    async def _manage_positions(
        self, state: MultiState, track_tasks: dict[str, asyncio.Task]
    ) -> None:
        config = state.config

        candles_updated = SlotBarrier(state.symbol_states.keys())
        trackers_ready: dict[str, Event] = {
            s: Event(autoclear=True) for s in state.symbol_states.keys()
        }
        for symbol, symbol_state in state.symbol_states.items():
            track_tasks[symbol] = create_task_cancel_owner_on_exception(
                self._track_advice(state, symbol_state, candles_updated, trackers_ready[symbol])
            )

        interval_offset = self._informant.get_interval_offset(config.exchange, config.interval)
        end = floor_multiple_offset(config.end, config.interval, interval_offset)
        while True:
            # Wait until we've received candle updates for all symbols.
            await candles_updated.wait()

            await self._try_close_existing_positions(state)
            await self._try_open_new_positions(state)

            # Repick top symbols. Do not repick during adjusted start period.
            if state.next_ > state.start:
                top_symbols = await self._find_top_symbols(config)
                leaving_symbols = [
                    s for s, ss in state.symbol_states.items()
                    if not ss.open_position and s not in top_symbols
                ]
                new_symbols = [
                    s for s in top_symbols if s not in state.symbol_states.keys()
                ][:len(leaving_symbols)]
                assert len(leaving_symbols) == len(new_symbols)

                if len(new_symbols) > 0:
                    msg = f'swapping out {leaving_symbols} in favor of {new_symbols}'
                    _log.info(msg)
                    await self._events.emit(config.channel, 'message', msg)

                    await cancel(*(track_tasks[s] for s in leaving_symbols))
                    for leaving_symbol in leaving_symbols:
                        del track_tasks[leaving_symbol]
                        del trackers_ready[leaving_symbol]
                        candles_updated.delete(leaving_symbol)
                        del state.symbol_states[leaving_symbol]

                    for new_symbol in new_symbols:
                        symbol_state = self._create_symbol_state(new_symbol, state.next_, config)
                        state.symbol_states[new_symbol] = symbol_state
                        candles_updated.add(new_symbol)
                        tracker_ready: Event = Event(autoclear=True)
                        trackers_ready[new_symbol] = tracker_ready
                        track_tasks[new_symbol] = create_task_cancel_owner_on_exception(
                            self._track_advice(state, symbol_state, candles_updated, tracker_ready)
                        )

            # Rebalance quotes.
            if len(state.quotes) > 1 and rpstdev(state.quotes) > 0.05:
                old_quotes = state.quotes
                state.quotes = self._split_quote(
                    sum(old_quotes, Decimal('0.0')), len(old_quotes), config.exchange
                )
                msg = f'rebalanced existing available quotes {old_quotes} as {state.quotes}'
                _log.info(msg)
                await self._events.emit(config.channel, 'message', msg)

            # Clear barrier for next update.
            candles_updated.clear()
            for e in trackers_ready.values():
                e.set()

            # Exit if last candle.
            if state.next_ >= end:
                for ss in state.symbol_states.values():
                    _log.info(f'{ss.symbol} last candle: {ss.last_candle}')
                break

    async def _try_close_existing_positions(self, state: MultiState) -> None:
        config = state.config

        queue = self._queues[state.id]
        await queue.join()

        to_process: list[Coroutine[None, None, Position.Closed]] = []
        for ss in (ss for ss in state.symbol_states.values() if ss.ready):
            assert ss.last_candle
            if (
                isinstance(ss.open_position, Position.OpenLong)
                and ss.advice in [Advice.LIQUIDATE, Advice.SHORT]
            ):
                to_process.append(
                    self._close_long_position(state, ss, ss.last_candle, ss.reason)
                )
            elif (
                isinstance(ss.open_position, Position.OpenShort)
                and ss.advice in [Advice.LIQUIDATE, Advice.LONG]
            ):
                to_process.append(
                    self._close_short_position(state, ss, ss.last_candle, ss.reason)
                )
        if len(to_process) > 0:
            positions = await process_task_on_queue(queue, asyncio.gather(*to_process))
            await self._events.emit(
                config.channel, 'positions_closed', positions, state.summary
            )

    async def _try_open_new_positions(self, state: MultiState) -> None:
        config = state.config

        queue = self._queues[state.id]
        await queue.join()

        to_process: list[Coroutine[None, None, Position.Open]] = []
        count = sum(1 for ss in state.symbol_states.values() if ss.open_position)
        assert count <= config.position_count
        available = config.position_count - count
        if state.open_new_positions:
            for ss in (ss for ss in state.symbol_states.values() if ss.ready):
                if available == 0:
                    break

                if ss.open_position:
                    continue

                assert ss.last_candle
                advice_age_valid = (
                    (ss.changed.prevailing_advice_age - 1) <= config.allowed_age_drift
                )
                if ss.advice is Advice.LONG and advice_age_valid:
                    to_process.append(self._open_long_position(state, ss, ss.last_candle))
                    available -= 1
                elif ss.advice is Advice.SHORT and advice_age_valid:
                    to_process.append(self._open_short_position(state, ss, ss.last_candle))
                    available -= 1

        if len(to_process) > 0:
            positions = await process_task_on_queue(queue, asyncio.gather(*to_process))
            await self._events.emit(
                config.channel, 'positions_opened', positions, state.summary
            )

    async def _track_advice(
        self, state: MultiState, symbol_state: _SymbolState, candles_updated: SlotBarrier,
        ready: Event
    ) -> None:
        config = state.config
        _log.info(f'tracking {symbol_state.symbol} candles')

        async for candle in self._chandler.stream_candles(
            exchange=config.exchange,
            symbol=symbol_state.symbol,
            interval=config.interval,
            start=symbol_state.next_,
            end=config.end,
            fill_missing_with_last=True,
            exchange_timeout=config.exchange_candle_timeout,
        ):
            current = symbol_state.next_
            if current < symbol_state.start:
                # Do not signal position manager during warm-up (adjusted start) period.
                advice, _reason = self._process_candle(state, symbol_state, candle)
                if advice is not Advice.NONE:
                    msg = (
                        f'received {symbol_state.symbol} advice {advice.name} during strategy '
                        f'warm-up period: adjusted start '
                        f'{strftimestamp(symbol_state.adjusted_start)}; actual start '
                        f'{strftimestamp(symbol_state.start)}; current {strftimestamp(current)}'
                    )
                    _log.warning(msg)
                    await self._events.emit(config.channel, 'message', msg)
            else:
                # Perform empty ticks when missing initial candles.
                initial_missed = False
                if (time_diff := candle.time - symbol_state.next_) > 0:
                    assert not initial_missed
                    assert symbol_state.next_ <= symbol_state.start
                    initial_missed = True
                    num_missed = time_diff // config.interval
                    _log.info(f'missed {num_missed} initial {symbol_state.symbol} candles')
                    for _ in range(num_missed):
                        await self._process_advice(
                            symbol_state, candles_updated, ready, Advice.NONE, CloseReason.STRATEGY
                        )

                advice, reason = self._process_candle(
                    state, symbol_state, candle
                )
                await self._process_advice(symbol_state, candles_updated, ready, advice, reason)

    def _process_candle(
        self, state: MultiState, symbol_state: _SymbolState, candle: Candle
    ) -> tuple[Advice, CloseReason]:
        config = state.config

        symbol_state.stop_loss.update(candle)
        symbol_state.take_profit.update(candle)
        symbol_state.strategy.update(candle)
        advice = symbol_state.strategy.advice
        reason = CloseReason.STRATEGY
        if (
            isinstance(symbol_state.open_position, Position.OpenLong)
            and advice not in [Advice.SHORT, Advice.LIQUIDATE]
        ):
            if symbol_state.stop_loss.upside_hit:
                _log.info(
                    f'{symbol_state.symbol} upside stop loss hit at {config.stop_loss} (trailing: '
                    f'{config.trail_stop_loss}); liquidating'
                )
                advice = Advice.LIQUIDATE
                reason = CloseReason.STOP_LOSS
            elif symbol_state.take_profit.upside_hit:
                _log.info(
                    f'{symbol_state.symbol} upside take profit hit at {config.take_profit}; '
                    'liquidating'
                )
                advice = Advice.LIQUIDATE
                reason = CloseReason.TAKE_PROFIT
        elif (
            isinstance(symbol_state.open_position, Position.OpenShort)
            and advice not in [Advice.LONG, Advice.LIQUIDATE]
        ):
            if symbol_state.stop_loss.downside_hit:
                _log.info(
                    f'{symbol_state.symbol} downside stop loss hit at {config.stop_loss} '
                    f'(trailing: {config.trail_stop_loss}); liquidating'
                )
                advice = Advice.LIQUIDATE
                reason = CloseReason.STOP_LOSS
            elif symbol_state.take_profit.downside_hit:
                _log.info(
                    f'{symbol_state.symbol} downside take profit hit at {config.take_profit}; '
                    'liquidating'
                )
                advice = Advice.LIQUIDATE
                reason = CloseReason.TAKE_PROFIT

        if not symbol_state.open_position:
            if (config.long and advice is Advice.LONG or config.short and advice is Advice.SHORT):
                symbol_state.stop_loss.clear(candle)
                symbol_state.take_profit.clear(candle)

        if not symbol_state.first_candle:
            _log.info(f'{symbol_state.symbol} first candle: {candle}')
            symbol_state.first_candle = candle
        symbol_state.last_candle = candle
        symbol_state.next_ = candle.time + config.interval
        state.next_ = max(state.next_, symbol_state.next_)

        return advice, reason

    async def _process_advice(
        self, symbol_state: _SymbolState, candles_updated: SlotBarrier, ready: Event,
        advice: Advice, reason: CloseReason
    ) -> None:
        _log.debug(f'{symbol_state.symbol} received advice: {advice.name} {reason.name}')

        # If the advice is overridden by stop loss or take profit, we don't want to affect the
        # strategy related `changed` filter.
        if reason in [CloseReason.STOP_LOSS, CloseReason.TAKE_PROFIT]:
            symbol_state.advice = advice
        else:
            # We use prevailing advice here because the configuration may allow an action based
            # on an advice given in the past.
            symbol_state.changed.update(advice)
            symbol_state.advice = symbol_state.changed.prevailing_advice

        symbol_state.reason = reason

        candles_updated.release(symbol_state.symbol)
        await ready.wait()

    async def close_positions(
        self, state: MultiState, symbols: list[str], reason: CloseReason
    ) -> list[Position.Closed]:
        if len(symbols) == 0:
            return []
        if not state.running:
            raise PositionNotOpen('Trader not running')
        queue = self._queues[state.id]
        if queue.qsize() > 0:
            raise PositionNotOpen('Process with position already pending')
        symbol_states = [
            ss
            for ss in (state.symbol_states.get(s) for s in symbols)
            if ss and ss.open_position
        ]
        if len(symbol_states) != len(symbols):
            raise PositionNotOpen(f'Attempted to close positions {symbols} but not all open')
        return await process_task_on_queue(
            queue,
            self._close_positions(state, symbol_states, reason),
        )

    async def _close_positions(
        self, state: MultiState, symbol_states: list[_SymbolState], reason: CloseReason
    ) -> list[Position.Closed]:
        if len(symbol_states) == 0:
            return []

        _log.info(f'closing {len(symbol_states)} open position(s)')
        positions = await asyncio.gather(
            *(self._close_position(state, ss, reason) for ss in symbol_states)
        )
        await self._events.emit(
            state.config.channel, 'positions_closed', positions, state.summary
        )
        return positions

    async def _close_position(
        self, state: MultiState, symbol_state: _SymbolState, reason: CloseReason
    ) -> Position.Closed:
        assert symbol_state.open_position
        assert symbol_state.last_candle
        if isinstance(symbol_state.open_position, Position.OpenLong):
            _log.info(f'{symbol_state.symbol} long position open; closing')
            return await self._close_long_position(
                state, symbol_state, symbol_state.last_candle, reason
            )
        elif isinstance(symbol_state.open_position, Position.OpenShort):
            _log.info(f'{symbol_state.symbol} short position open; closing')
            return await self._close_short_position(
                state, symbol_state, symbol_state.last_candle, reason
            )

    async def _open_long_position(
        self, state: MultiState, symbol_state: _SymbolState, candle: Candle
    ) -> Position.OpenLong:
        config = state.config
        assert state.quotes
        symbol_state.allocated_quote = state.quotes.pop(0)

        position = (
            self.open_simulated_long_position(
                exchange=config.exchange,
                symbol=symbol_state.symbol,
                time=candle.time + config.interval,
                price=candle.close,
                quote=symbol_state.allocated_quote,
            )
            if config.mode is TradingMode.BACKTEST else
            await self.open_long_position(
                exchange=config.exchange,
                symbol=symbol_state.symbol,
                quote=symbol_state.allocated_quote,
                mode=config.mode,
            )
        )

        symbol_state.allocated_quote += position.quote_delta()
        symbol_state.open_position = position

        return position

    async def _close_long_position(
        self, state: MultiState, symbol_state: _SymbolState, candle: Candle,
        reason: CloseReason
    ) -> Position.Long:
        config = state.config
        assert state.summary
        assert state.quotes is not None
        assert isinstance(symbol_state.open_position, Position.OpenLong)

        position = (
            self.close_simulated_long_position(
                position=symbol_state.open_position,
                time=candle.time + config.interval,
                price=candle.close,
                reason=reason,
            )
            if config.mode is TradingMode.BACKTEST else
            await self.close_long_position(
                position=symbol_state.open_position,
                mode=config.mode,
                reason=reason,
            )
        )

        symbol_state.allocated_quote += position.quote_delta()
        state.quotes.append(symbol_state.allocated_quote)
        symbol_state.allocated_quote = Decimal('0.0')

        state.summary.append_position(position)
        symbol_state.open_position = None

        return position

    async def _open_short_position(
        self, state: MultiState, symbol_state: _SymbolState, candle: Candle
    ) -> Position.OpenShort:
        config = state.config
        assert state.quotes
        symbol_state.allocated_quote = state.quotes.pop(0)

        position = (
            self.open_simulated_short_position(
                exchange=config.exchange,
                symbol=symbol_state.symbol,
                time=candle.time + config.interval,
                price=candle.close,
                collateral=symbol_state.allocated_quote,
            )
            if config.mode is TradingMode.BACKTEST else
            await self.open_short_position(
                exchange=config.exchange,
                symbol=symbol_state.symbol,
                collateral=symbol_state.allocated_quote,
                mode=config.mode,
            )
        )

        symbol_state.allocated_quote += position.quote_delta()
        symbol_state.open_position = position

        return position

    async def _close_short_position(
        self, state: MultiState, symbol_state: _SymbolState, candle: Candle,
        reason: CloseReason
    ) -> Position.Short:
        config = state.config
        assert state.summary
        assert state.quotes is not None
        assert isinstance(symbol_state.open_position, Position.OpenShort)

        position = (
            self.close_simulated_short_position(
                position=symbol_state.open_position,
                time=candle.time + config.interval,
                price=candle.close,
                reason=reason,
            )
            if config.mode is TradingMode.BACKTEST else
            await self.close_short_position(
                position=symbol_state.open_position,
                mode=config.mode,
                reason=reason,
            )
        )

        symbol_state.allocated_quote += position.quote_delta()
        state.quotes.append(symbol_state.allocated_quote)
        symbol_state.allocated_quote = Decimal('0.0')

        state.summary.append_position(position)
        symbol_state.open_position = None

        return position
