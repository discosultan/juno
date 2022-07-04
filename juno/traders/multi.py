from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Optional, TypeVar
from uuid import uuid4

from more_itertools import take

from juno import Advice, Candle, Interval, Timestamp
from juno.asyncio import (
    Event,
    SlotBarrier,
    cancel,
    create_task_cancel_owner_on_exception,
    process_task_on_queue,
)
from juno.brokers import Broker
from juno.components import Chandler, Events, Informant, User
from juno.custodians import Custodian, Stub
from juno.inspect import Constructor
from juno.math import rpstdev, split
from juno.positioner import Positioner, SimulatedPositioner
from juno.stop_loss import Noop as NoopStopLoss
from juno.stop_loss import StopLoss
from juno.strategies import Changed, Signal
from juno.take_profit import Noop as NoopTakeProfit
from juno.take_profit import TakeProfit
from juno.time import floor_timestamp, strftimestamp, time_ms
from juno.trading import CloseReason, Position, StartMixin, TradingMode, TradingSummary

from .trader import Trader

_log = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class MultiConfig:
    exchange: str
    interval: Interval
    end: Timestamp
    strategy: Constructor[Signal]
    # Overrides default strategy.
    symbol_strategies: dict[str, Constructor[Signal]] = field(default_factory=dict)
    stop_loss: Optional[Constructor[StopLoss]] = None
    take_profit: Optional[Constructor[TakeProfit]] = None
    start: Optional[Timestamp] = None  # None means max earliest is found.
    quote: Optional[Decimal] = None  # None means exchange wallet is queried.
    trail_stop_loss: bool = True
    adjust_start: bool = True
    mode: TradingMode = TradingMode.BACKTEST
    channel: str = "default"
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
    quote_asset: str = "btc"
    repick_symbols: bool = True
    custodian: str = "stub"


@dataclass
class MultiState:
    config: MultiConfig
    close_on_exit: bool
    symbol_states: dict[str, _SymbolState]
    starting_quote: Decimal
    quotes: list[Decimal]
    candle_start: Timestamp  # Candle time.
    start: Timestamp  # Trading start, real time.
    next_: Timestamp  # Candle time.
    real_start: Timestamp
    open_new_positions: bool = True  # Whether new positions can be opened.
    positions: list[Position.Closed] = field(default_factory=list)

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
    allocated_quote: Decimal = Decimal("0.0")
    first_candle: Optional[Candle] = None
    last_candle: Optional[Candle] = None
    advice: Advice = Advice.NONE
    advice_age: int = 0
    reason: CloseReason = CloseReason.STRATEGY

    @property
    def ready(self) -> bool:
        return self.first_candle is not None


class Multi(Trader[MultiConfig, MultiState], StartMixin):
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
        custodians: list[Custodian] = [Stub()],
        events: Events = Events(),
        get_time_ms: Callable[[], int] = time_ms,
    ) -> None:
        self._chandler = chandler
        self._informant = informant
        self._broker = broker
        if user is not None and broker is not None:
            self._positioner = Positioner(
                informant=informant,
                chandler=chandler,
                broker=broker,
                user=user,
                custodians=custodians,
            )
        self._simulated_positioner = SimulatedPositioner(informant=informant)
        self._custodians = {type(c).__name__.lower(): c for c in custodians}
        self._events = events
        self._get_time_ms = get_time_ms
        self._queues: dict[str, asyncio.Queue] = {}  # Key: state id

    @property
    def chandler(self) -> Chandler:
        return self._chandler

    @property
    def broker(self) -> Broker:
        assert self._broker
        return self._broker

    async def initialize(self, config: MultiConfig) -> MultiState:
        assert config.mode is TradingMode.BACKTEST or self._positioner
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

        quote = await self._custodians[config.custodian].request_quote(
            exchange=config.exchange, asset=config.quote_asset, quote=config.quote
        )
        position_quote = quote / config.position_count
        for symbol in symbols:
            _, filters = self._informant.get_fees_filters(config.exchange, symbol)
            assert position_quote > filters.price.min

        return MultiState(
            config=config,
            close_on_exit=config.close_on_exit,
            real_start=real_start,
            candle_start=start,
            next_=start,
            starting_quote=quote,
            quotes=self._split_quote(
                config.quote_asset, quote, config.position_count, config.exchange
            ),
            start=start if config.mode is TradingMode.BACKTEST else real_start,
            symbol_states={s: self._create_symbol_state(s, start, config) for s in symbols},
        )

    def _split_quote(self, asset: str, quote: Decimal, parts: int, exchange: str) -> list[Decimal]:
        asset_info = self._informant.get_asset_info(exchange, asset)
        return split(quote, parts, asset_info.precision)

    def _create_symbol_state(self, symbol: str, start: int, config: MultiConfig) -> _SymbolState:
        strategy = config.symbol_strategies.get(symbol, config.strategy).construct()

        adjusted_start = start
        if config.adjust_start:
            _log.info(
                f"fetching {strategy.maturity - 1} {symbol} candle(s) before start time to "
                "warm-up strategy"
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
                NoopStopLoss() if config.stop_loss is None else config.stop_loss.construct()
            ),
            take_profit=(
                NoopTakeProfit() if config.take_profit is None else config.take_profit.construct()
            ),
        )

    async def run(self, state: MultiState) -> TradingSummary:
        config = state.config
        msg = (
            f"managing up to {config.position_count} positions by tracking top "
            f"{config.track_count} symbols by volume: {list(state.symbol_states.keys())}"
        )
        _log.info(msg)
        await self._events.emit(config.channel, "message", msg)
        _log.info(f"quote split as: {state.quotes}")

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
                    [
                        (ss, CloseReason.CANCELLED)
                        for ss in state.symbol_states.values()
                        if ss.open_position
                    ],
                )

        _log.info("finished")
        return self.build_summary(state)

    async def _find_top_symbols(self, config: MultiConfig) -> list[str]:
        symbol_pattern = f"*-{config.quote_asset}"
        tickers = self._informant.map_tickers(
            config.exchange,
            symbol_patterns=[symbol_pattern],
            exclude_symbol_patterns=config.track_exclude,
            spot=True,
            isolated_margin=True,
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
                s: t
                for (s, t), c in zip(tickers.items(), first_candles)
                if c.time <= config.track_required_start
            }
        # Validate.
        if len(tickers) < config.track_count:
            required_start_msg = (
                ""
                if config.track_required_start is None
                else f" with required start at {strftimestamp(config.track_required_start)}"
            )
            raise ValueError(
                f"Exchange only supports {len(tickers)} symbols matching pattern {symbol_pattern} "
                f"while {config.track_count} requested{required_start_msg}"
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

        end = floor_timestamp(config.end, config.interval)
        while True:
            # Wait until we've received candle updates for all symbols.
            await candles_updated.wait()

            await self._try_close_existing_positions(state)
            await self._try_open_new_positions(state)

            # Repick top symbols. Do not repick during adjusted start period.
            if config.repick_symbols and state.next_ > state.candle_start:
                top_symbols = await self._find_top_symbols(config)
                leaving_symbols = [
                    s
                    for s, ss in state.symbol_states.items()
                    if not ss.open_position and s not in top_symbols
                ]
                new_symbols = [s for s in top_symbols if s not in state.symbol_states.keys()][
                    : len(leaving_symbols)
                ]
                assert len(leaving_symbols) == len(new_symbols)

                if len(new_symbols) > 0:
                    msg = f"swapping out {leaving_symbols} in favor of {new_symbols}"
                    _log.info(msg)
                    await self._events.emit(config.channel, "message", msg)

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
                    config.quote_asset,
                    sum(old_quotes, Decimal("0.0")),
                    len(old_quotes),
                    config.exchange,
                )
                msg = f"rebalanced existing available quotes {old_quotes} as {state.quotes}"
                _log.info(msg)
                await self._events.emit(config.channel, "message", msg)

            # Clear barrier for next update.
            candles_updated.clear()
            for e in trackers_ready.values():
                e.set()

            # Exit if last candle.
            if state.next_ >= end:
                for ss in state.symbol_states.values():
                    _log.info(f"{ss.symbol} last candle: {ss.last_candle}")
                break

    async def _try_close_existing_positions(self, state: MultiState) -> None:
        queue = self._queues[state.id]
        await queue.join()

        to_process: list[tuple[_SymbolState, CloseReason]] = []
        for symbol_state in (ss for ss in state.symbol_states.values() if ss.ready):
            assert symbol_state.last_candle
            if isinstance(
                symbol_state.open_position, Position.OpenLong
            ) and symbol_state.advice in {
                Advice.LIQUIDATE,
                Advice.SHORT,
            }:
                to_process.append((symbol_state, symbol_state.reason))
            elif isinstance(
                symbol_state.open_position, Position.OpenShort
            ) and symbol_state.advice in {
                Advice.LIQUIDATE,
                Advice.LONG,
            }:
                to_process.append((symbol_state, symbol_state.reason))
        if len(to_process) > 0:
            await process_task_on_queue(queue, self._close_positions(state, to_process))

    async def _try_open_new_positions(self, state: MultiState) -> None:
        config = state.config

        queue = self._queues[state.id]
        await queue.join()

        to_process: list[tuple[_SymbolState, bool]] = []  # [symbol state, short]
        count = sum(1 for ss in state.symbol_states.values() if ss.open_position)
        assert count <= config.position_count
        available = config.position_count - count
        if state.open_new_positions:
            for symbol_state in (ss for ss in state.symbol_states.values() if ss.ready):
                if available == 0:
                    break

                if symbol_state.open_position:
                    continue

                assert symbol_state.last_candle
                advice_age_valid = (
                    symbol_state.changed.prevailing_advice_age - 1
                ) <= config.allowed_age_drift
                if config.long and symbol_state.advice is Advice.LONG and advice_age_valid:
                    to_process.append((symbol_state, False))
                    available -= 1
                elif config.short and symbol_state.advice is Advice.SHORT and advice_age_valid:
                    to_process.append((symbol_state, True))
                    available -= 1

        if len(to_process) > 0:
            await process_task_on_queue(queue, self._open_positions(state, to_process))

    async def _track_advice(
        self,
        state: MultiState,
        symbol_state: _SymbolState,
        candles_updated: SlotBarrier,
        ready: Event,
    ) -> None:
        config = state.config
        _log.info(f"tracking {symbol_state.symbol} candles")

        last_candle: Optional[Candle] = None
        async for candle in self._chandler.stream_candles_fill_missing_with_none(
            exchange=config.exchange,
            symbol=symbol_state.symbol,
            interval=config.interval,
            start=symbol_state.next_,
            end=config.end,
            exchange_timeout=config.exchange_candle_timeout,
        ):
            # Skip initial empty candles.
            if not last_candle and not candle:
                continue

            if not candle:
                assert last_candle
                # TODO: Not nice. We should proceed a symbol state without updating a strategy with
                # a previous candle.
                candle = last_candle

            current = symbol_state.next_
            if current < symbol_state.start:
                # Do not signal position manager during warm-up (adjusted start) period.
                advice, _reason = self._process_candle(state, symbol_state, candle)
                if advice is not Advice.NONE:
                    msg = (
                        f"received {symbol_state.symbol} advice {advice.name} during strategy "
                        f"warm-up period: adjusted start "
                        f"{strftimestamp(symbol_state.adjusted_start)}; actual start "
                        f"{strftimestamp(symbol_state.start)}; current {strftimestamp(current)}"
                    )
                    _log.warning(msg)
                    await self._events.emit(config.channel, "message", msg)
            else:
                # Perform empty ticks when missing initial candles.
                assert candle
                initial_missed = False
                if (time_diff := candle.time - symbol_state.next_) > 0:
                    assert not initial_missed
                    assert symbol_state.next_ <= symbol_state.start
                    initial_missed = True
                    num_missed = time_diff // config.interval
                    _log.info(f"missed {num_missed} initial {symbol_state.symbol} candles")
                    for _ in range(num_missed):
                        await self._process_advice(
                            symbol_state, candles_updated, ready, Advice.NONE, CloseReason.STRATEGY
                        )

                advice, reason = self._process_candle(state, symbol_state, candle)
                await self._process_advice(symbol_state, candles_updated, ready, advice, reason)
            if candle:
                last_candle = candle

    def _process_candle(
        self, state: MultiState, symbol_state: _SymbolState, candle: Candle
    ) -> tuple[Advice, CloseReason]:
        config = state.config

        symbol_state.stop_loss.update(candle)
        symbol_state.take_profit.update(candle)
        symbol_state.strategy.update(candle, (symbol_state.symbol, config.interval, "regular"))
        advice = symbol_state.strategy.advice
        reason = CloseReason.STRATEGY
        if isinstance(symbol_state.open_position, Position.OpenLong) and advice not in [
            Advice.SHORT,
            Advice.LIQUIDATE,
        ]:
            if symbol_state.stop_loss.upside_hit:
                _log.info(
                    f"{symbol_state.symbol} upside stop loss hit at {config.stop_loss} (trailing: "
                    f"{config.trail_stop_loss}); liquidating"
                )
                advice = Advice.LIQUIDATE
                reason = CloseReason.STOP_LOSS
            elif symbol_state.take_profit.upside_hit:
                _log.info(
                    f"{symbol_state.symbol} upside take profit hit at {config.take_profit}; "
                    "liquidating"
                )
                advice = Advice.LIQUIDATE
                reason = CloseReason.TAKE_PROFIT
        elif isinstance(symbol_state.open_position, Position.OpenShort) and advice not in [
            Advice.LONG,
            Advice.LIQUIDATE,
        ]:
            if symbol_state.stop_loss.downside_hit:
                _log.info(
                    f"{symbol_state.symbol} downside stop loss hit at {config.stop_loss} "
                    f"(trailing: {config.trail_stop_loss}); liquidating"
                )
                advice = Advice.LIQUIDATE
                reason = CloseReason.STOP_LOSS
            elif symbol_state.take_profit.downside_hit:
                _log.info(
                    f"{symbol_state.symbol} downside take profit hit at {config.take_profit}; "
                    "liquidating"
                )
                advice = Advice.LIQUIDATE
                reason = CloseReason.TAKE_PROFIT

        if not symbol_state.open_position:
            if config.long and advice is Advice.LONG or config.short and advice is Advice.SHORT:
                symbol_state.stop_loss.clear(candle)
                symbol_state.take_profit.clear(candle)

        if not symbol_state.first_candle:
            _log.info(f"{symbol_state.symbol} first candle: {candle}")
            symbol_state.first_candle = candle
        symbol_state.last_candle = candle
        symbol_state.next_ = candle.time + config.interval
        state.next_ = max(state.next_, symbol_state.next_)

        return advice, reason

    async def _process_advice(
        self,
        symbol_state: _SymbolState,
        candles_updated: SlotBarrier,
        ready: Event,
        advice: Advice,
        reason: CloseReason,
    ) -> None:
        _log.debug(f"{symbol_state.symbol} received advice: {advice.name} {reason.name}")

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

    async def open_positions(
        self, state: MultiState, symbols: list[str], short: bool
    ) -> list[Position.Open]:
        if len(symbols) == 0:
            return []

        queue = self._queues[state.id]
        allowed_symbols = set(state.symbol_states.keys())
        open_symbols = {ss.symbol for ss in state.symbol_states.values() if ss.open_position}
        cannot_open_symbols = set(symbols) & open_symbols
        to_process = [ss for ss in state.symbol_states.values() if ss.symbol in symbols]

        if not state.running:
            raise ValueError("Trader not running")
        if queue.qsize() > 0:
            raise ValueError("Process with position already pending")
        if not all(s in allowed_symbols for s in symbols):
            raise ValueError(f"Can only open {allowed_symbols} positions")
        if state.config.position_count - len(open_symbols) < len(symbols):
            raise ValueError("Cannot open all the positions due to position limit")
        if len(cannot_open_symbols) > 0:
            raise ValueError(f"Cannot open already open {cannot_open_symbols} positions")
        if not all(ss.last_candle for ss in to_process):
            raise ValueError("No candle received for all symbols yet")

        return await process_task_on_queue(
            queue,
            self._open_positions(state, [(ss, short) for ss in to_process]),
        )

    async def close_positions(
        self, state: MultiState, symbols: list[str], reason: CloseReason
    ) -> list[Position.Closed]:
        if len(symbols) == 0:
            return []

        queue = self._queues[state.id]
        allowed_symbols = set(state.symbol_states.keys())
        open_symbols = {ss.symbol for ss in state.symbol_states.values() if ss.open_position}
        cannot_close_symbols = set(symbols) - open_symbols
        symbol_states_to_process = [
            ss for ss in state.symbol_states.values() if ss.symbol in symbols
        ]

        if not state.running:
            raise ValueError("Trader not running")
        if queue.qsize() > 0:
            raise ValueError("Process with position already pending")
        if not all(s in allowed_symbols for s in symbols):
            raise ValueError(f"Can only open {allowed_symbols} positions")
        if len(open_symbols) == 0:
            raise ValueError("No positions open")
        if len(cannot_close_symbols) > 0:
            raise ValueError(f"Cannot close already close {cannot_close_symbols} positions")
        if not all(ss.last_candle for ss in symbol_states_to_process):
            raise ValueError("No candle received for all symbols yet")

        return await process_task_on_queue(
            queue,
            self._close_positions(
                state,
                [(ss, reason) for ss in state.symbol_states.values() if ss.symbol in symbols],
            ),
        )

    async def _open_positions(
        self,
        state: MultiState,
        entries: list[tuple[_SymbolState, bool]],  # [symbol state, short]
    ) -> list[Position.Open]:
        if len(entries) == 0:
            return []

        config = state.config
        _log.info(f"opening {len(entries)} position(s)")

        for symbol_state, _ in entries:
            assert symbol_state.last_candle
            symbol_state.allocated_quote = state.quotes.pop(0)

        positions = (
            self._simulated_positioner.open_simulated_positions(
                exchange=config.exchange,
                entries=[
                    (
                        ss.symbol,
                        ss.allocated_quote,
                        short,
                        ss.last_candle.time + config.interval,  # type: ignore
                        ss.last_candle.close,  # type: ignore
                    )
                    for ss, short in entries
                ],
            )
            if config.mode is TradingMode.BACKTEST
            else await self._positioner.open_positions(
                exchange=config.exchange,
                custodian=config.custodian,
                mode=config.mode,
                entries=[(ss.symbol, ss.allocated_quote, short) for ss, short in entries],
            )
        )

        for (symbol_state, _), position in zip(entries, positions):
            symbol_state.allocated_quote -= position.cost
            symbol_state.open_position = position

        await self._events.emit(
            state.config.channel, "positions_opened", positions, self.build_summary(state)
        )
        return positions

    async def _close_positions(
        self,
        state: MultiState,
        entries: list[tuple[_SymbolState, CloseReason]],
    ) -> list[Position.Closed]:
        if len(entries) == 0:
            return []

        assert state.quotes is not None

        config = state.config
        _log.info(f"closing {len(entries)} open position(s)")

        for symbol_state, _ in entries:
            assert symbol_state.open_position
            assert symbol_state.last_candle

        positions = (
            self._simulated_positioner.close_simulated_positions(
                entries=[
                    (
                        ss.open_position,
                        reason,
                        ss.last_candle.time + config.interval,  # type: ignore
                        ss.last_candle.close,  # type: ignore
                    )
                    for ss, reason in entries
                ],
            )
            if config.mode is TradingMode.BACKTEST
            else await self._positioner.close_positions(
                custodian=config.custodian,
                mode=config.mode,
                entries=[(ss.open_position, reason) for ss, reason in entries],  # type: ignore
            )
        )

        for (symbol_state, _), position in zip(entries, positions):
            symbol_state.allocated_quote += position.gain
            state.quotes.append(symbol_state.allocated_quote)
            symbol_state.allocated_quote = Decimal("0.0")

            state.positions.append(position)
            symbol_state.open_position = None

        await self._events.emit(
            state.config.channel, "positions_closed", positions, self.build_summary(state)
        )
        return positions

    def build_summary(self, state: MultiState) -> TradingSummary:
        config = state.config
        if config.end is not None and config.end <= state.real_start:  # Backtest.
            end = (
                max(s.last_candle.time for s in state.symbol_states.values() if s.last_candle)
                + config.interval
                if any(s.last_candle for s in state.symbol_states.values())
                else state.start + config.interval
            )
        else:  # Paper or live.
            end = min(self._get_time_ms(), config.end)

        return TradingSummary(
            start=state.start,
            end=end,
            starting_assets={
                state.config.quote_asset: state.starting_quote,
            },
            positions=list(state.positions),
        )
