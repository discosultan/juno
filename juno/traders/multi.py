from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Coroutine, Dict, List, Optional, Tuple, Type

from more_itertools import take

from juno import Advice, Candle, Interval, Timestamp
from juno.asyncio import Event, SlotBarrier
from juno.brokers import Broker
from juno.components import Chandler, Events, Informant, User
from juno.exchanges import Exchange
from juno.math import floor_multiple
from juno.strategies import Changed, Signal
from juno.time import strftimestamp, time_ms
from juno.trading import (
    CloseReason, Position, PositionMixin, SimulatedPositionMixin, StartMixin, StopLoss, TakeProfit,
    TradingMode, TradingSummary
)
from juno.typing import TypeConstructor

from .trader import Trader

_log = logging.getLogger(__name__)

SYMBOL_PATTERN = '*-btc'


@dataclass(frozen=True)
class MultiConfig:
    exchange: str
    interval: Interval
    end: Timestamp
    strategy: TypeConstructor[Signal]
    # Overrides default strategy.
    symbol_strategies: Dict[str, TypeConstructor[Signal]] = field(default_factory=dict)
    start: Optional[Timestamp] = None  # None means max earliest is found.
    quote: Optional[Decimal] = None  # None means exchange wallet is queried.
    stop_loss: Decimal = Decimal('0.0')  # 0 means disabled.
    trail_stop_loss: bool = True
    take_profit: Decimal = Decimal('0.0')  # 0 means disabled.
    adjust_start: bool = True
    mode: TradingMode = TradingMode.BACKTEST
    channel: str = 'default'
    long: bool = True  # Take long positions.
    short: bool = False  # Take short positions.
    close_on_exit: bool = True  # Whether to close open positions on exit.
    track: List[str] = field(default_factory=list)
    track_exclude: List[str] = field(default_factory=list)  # Symbols to ignore.
    track_count: int = 4
    track_required_start: Optional[Timestamp] = None
    position_count: int = 2
    exchange_candle_timeout: Optional[Interval] = None


@dataclass
class MultiState:
    config: MultiConfig
    start: Timestamp
    symbol_states: Dict[str, _SymbolState]
    quotes: List[Decimal]
    summary: TradingSummary
    real_start: Timestamp
    symbols: List[str]
    open_new_positions: bool = True  # Whether new positions can be opened.

    @property
    def open_positions(self) -> List[Position.Open]:
        if not self.symbol_states:
            return []
        return [s.open_position for s in self.symbol_states.values() if s.open_position]


@dataclass
class _SymbolState:
    symbol: str
    strategy: Signal
    changed: Changed
    override_changed: Changed
    current: Timestamp
    stop_loss: StopLoss
    take_profit: TakeProfit
    start_adjusted: bool = False
    open_position: Optional[Position.Open] = None
    allocated_quote: Decimal = Decimal('0.0')
    first_candle: Optional[Candle] = None
    last_candle: Optional[Candle] = None
    override_reason: Optional[CloseReason] = None

    @property
    def ready(self) -> bool:
        return self.first_candle is not None

    @property
    def advice(self) -> Advice:
        return (
            self.changed.prevailing_advice
            if self.override_changed.prevailing_advice is Advice.NONE
            else self.override_changed.prevailing_advice
        )

    @property
    def advice_age(self) -> int:
        return (
            self.changed.prevailing_advice_age
            if self.override_changed.prevailing_advice is Advice.NONE
            else self.override_changed.prevailing_advice_age
        )

    @property
    def reason(self) -> CloseReason:
        if self.override_changed.prevailing_advice is Advice.NONE:
            return CloseReason.STRATEGY
        assert self.override_reason is not None
        return self.override_reason


class Multi(Trader[MultiConfig, MultiState], PositionMixin, SimulatedPositionMixin, StartMixin):
    @staticmethod
    def config() -> Type[MultiConfig]:
        return MultiConfig

    @staticmethod
    def state() -> Type[MultiState]:
        return MultiState

    def __init__(
        self,
        chandler: Chandler,
        informant: Informant,
        user: Optional[User] = None,
        broker: Optional[Broker] = None,
        events: Events = Events(),
        exchanges: List[Exchange] = [],
        get_time_ms: Callable[[], int] = time_ms,
    ) -> None:
        self._chandler = chandler
        self._informant = informant
        self._user = user
        self._broker = broker
        self._events = events
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._get_time_ms = get_time_ms

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
    def exchanges(self) -> Dict[str, Exchange]:
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
        assert StopLoss.is_valid(config.stop_loss)
        assert TakeProfit.is_valid(config.take_profit)
        assert config.position_count > 0
        assert config.position_count <= config.track_count
        assert len(config.track) <= config.track_count
        assert not list(set(config.track) & set(config.track_exclude))  # No common elements.

        symbols = await self._find_top_symbols(config)

        start = await self.request_start(config.start, config.exchange, symbols, [config.interval])

        quote = await self.request_quote(config.quote, config.exchange, 'btc', config.mode)
        position_quote = quote / config.position_count
        for symbol in symbols:
            fees, filters = self._informant.get_fees_filters(config.exchange, symbol)
            assert position_quote > filters.price.min

        return MultiState(
            config=config,
            symbols=symbols,
            real_start=self._get_time_ms(),
            start=start,
            quotes=[quote / config.position_count] * config.position_count,
            summary=TradingSummary(
                start=start,
                quote=quote,
                quote_asset='btc',  # TODO: support others
            ),
            symbol_states={
                s: _SymbolState(
                    symbol=s,
                    strategy=config.symbol_strategies.get(s, config.strategy).construct(),
                    changed=Changed(True),
                    override_changed=Changed(True),
                    current=start,
                    stop_loss=StopLoss(threshold=config.stop_loss, trail=config.trail_stop_loss),
                    take_profit=TakeProfit(threshold=config.take_profit),
                ) for s in symbols
            }
        )

    async def run(self, state: MultiState) -> TradingSummary:
        config = state.config
        _log.info(
            f'managing up to {config.position_count} positions by tracking top '
            f'{config.track_count} symbols: {list(state.symbol_states.keys())}'
        )
        _log.info(f'quote split as: {state.quotes}')

        try:
            candles_updated = SlotBarrier(state.symbol_states.keys())
            trackers_ready: Dict[str, Event] = {
                s: Event(autoclear=True) for s in state.symbol_states.keys()
            }
            await asyncio.gather(
                self._manage_positions(state, candles_updated, trackers_ready),
                *(self._track_advice(state, ss, candles_updated, trackers_ready[s])
                  for s, ss in state.symbol_states.items())
            )
        finally:
            if config.close_on_exit:
                await self._close_all_open_positions(state)
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

    async def _find_top_symbols(self, config: MultiConfig) -> List[str]:
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
        self, state: MultiState, candles_updated: SlotBarrier, trackers_ready: Dict[str, Event]
    ) -> None:
        config = state.config
        assert state.symbol_states
        final_candle_time = floor_multiple(config.end, config.interval) - config.interval
        to_process: List[Coroutine[None, None, Position.Any]] = []
        while True:
            # Wait until we've received candle updates for all symbols.
            await candles_updated.wait()

            # TODO: Rebalance quotes.
            # TODO: Repick top symbols.

            # Try close existing positions.
            to_process.clear()
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
                positions = await asyncio.gather(*to_process)
                await self._events.emit(
                    config.channel, 'positions_closed', positions, state.summary
                )

            # Try open new positions.
            to_process.clear()
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
                    # TODO: Be more flexible?
                    if ss.advice is Advice.LONG and ss.advice_age == 1:
                        to_process.append(self._open_long_position(state, ss, ss.last_candle))
                        available -= 1
                    elif ss.advice is Advice.SHORT and ss.advice_age == 1:
                        to_process.append(self._open_short_position(state, ss, ss.last_candle))
                        available -= 1

            if len(to_process) > 0:
                positions = await asyncio.gather(*to_process)
                await self._events.emit(
                    config.channel, 'positions_opened', positions, state.summary
                )

            # Clear barrier for next update.
            candles_updated.clear()
            for e in trackers_ready.values():
                e.set()

            # Exit if last candle.
            if (
                (last_candle := next(iter(state.symbol_states.values())).last_candle)
                and last_candle.time >= final_candle_time
            ):
                for ss in state.symbol_states.values():
                    _log.info(f'{ss.symbol} last candle: {last_candle}')
                break

    async def _track_advice(
        self, state: MultiState, symbol_state: _SymbolState, candles_updated: SlotBarrier,
        ready: Event
    ) -> None:
        config = state.config

        if config.adjust_start and not symbol_state.start_adjusted:
            _log.info(
                f'fetching {symbol_state.strategy.maturity - 1} {symbol_state.symbol} candle(s) '
                'before start time to warm-up strategy'
            )
            symbol_state.current = (
                max(
                    symbol_state.current - (symbol_state.strategy.maturity - 1) * config.interval,
                    0,
                )
            )
            symbol_state.start_adjusted = True

        async for candle in self._chandler.stream_candles(
            exchange=config.exchange,
            symbol=symbol_state.symbol,
            interval=config.interval,
            start=symbol_state.current,
            end=config.end,
            fill_missing_with_last=True,
            exchange_timeout=config.exchange_candle_timeout,
        ):
            # Perform empty ticks when missing initial candles.
            initial_missed = False
            if (time_diff := candle.time - symbol_state.current) > 0:
                assert not initial_missed
                assert symbol_state.current <= state.start
                initial_missed = True
                num_missed = time_diff // config.interval
                for _ in range(num_missed):
                    await self._process_advice(
                        symbol_state, candles_updated, ready, Advice.NONE, Advice.NONE, None
                    )

            advice, override_advice, override_reason = self._process_candle(
                config, symbol_state, candle
            )
            await self._process_advice(
                symbol_state, candles_updated, ready, advice, override_advice, override_reason
            )

    def _process_candle(
        self, config: MultiConfig, symbol_state: _SymbolState, candle: Candle
    ) -> Tuple[Advice, Advice, Optional[CloseReason]]:
        symbol_state.stop_loss.update(candle)
        symbol_state.take_profit.update(candle)
        symbol_state.strategy.update(candle)
        advice = symbol_state.strategy.advice
        override_advice = Advice.NONE
        override_reason = None
        if (
            isinstance(symbol_state.open_position, Position.OpenLong)
            and advice not in [Advice.SHORT, Advice.LIQUIDATE]
        ):
            if symbol_state.stop_loss.upside_hit:
                _log.info(
                    f'{symbol_state.symbol} upside stop loss hit at {config.stop_loss} (trailing: '
                    f'{config.trail_stop_loss}); liquidating'
                )
                override_advice = Advice.LIQUIDATE
                override_reason = CloseReason.STOP_LOSS
            elif symbol_state.take_profit.upside_hit:
                _log.info(
                    f'{symbol_state.symbol} upside take profit hit at {config.take_profit}; '
                    'liquidating'
                )
                override_advice = Advice.LIQUIDATE
                override_reason = CloseReason.TAKE_PROFIT
        elif (
            isinstance(symbol_state.open_position, Position.OpenShort)
            and advice not in [Advice.LONG, Advice.LIQUIDATE]
        ):
            if symbol_state.stop_loss.downside_hit:
                _log.info(
                    f'{symbol_state.symbol} downside stop loss hit at {config.stop_loss} '
                    f'(trailing: {config.trail_stop_loss}); liquidating'
                )
                override_advice = Advice.LIQUIDATE
                override_reason = CloseReason.STOP_LOSS
            elif symbol_state.take_profit.downside_hit:
                _log.info(
                    f'{symbol_state.symbol} downside take profit hit at {config.take_profit}; '
                    'liquidating'
                )
                override_advice = Advice.LIQUIDATE
                override_reason = CloseReason.TAKE_PROFIT

        if not symbol_state.open_position:
            if (config.long and advice is Advice.LONG or config.short and advice is Advice.SHORT):
                symbol_state.stop_loss.clear(candle)
                symbol_state.take_profit.clear(candle)

        if not symbol_state.first_candle:
            _log.info(f'{symbol_state.symbol} first candle: {candle}')
            symbol_state.first_candle = candle
        symbol_state.last_candle = candle
        symbol_state.current = candle.time + config.interval

        return advice, override_advice, override_reason

    async def _process_advice(
        self, symbol_state: _SymbolState, candles_updated: SlotBarrier, ready: Event,
        advice: Advice, override_advice: Advice, override_reason: Optional[CloseReason]
    ) -> None:
        _log.debug(f'{symbol_state.symbol} received advice: {advice.name} {override_advice.name}')

        if override_advice is not Advice.NONE:
            symbol_state.override_changed.update(override_advice)
        elif advice is not symbol_state.changed.prevailing_advice:
            symbol_state.override_changed.update(Advice.NONE)
        else:
            symbol_state.override_changed.update(symbol_state.override_changed.prevailing_advice)
        symbol_state.override_reason = override_reason

        symbol_state.changed.update(advice)

        candles_updated.release(symbol_state.symbol)
        await ready.wait()

    async def _close_all_open_positions(self, state: MultiState) -> None:
        config = state.config
        assert state.symbol_states
        to_close: List[Coroutine[None, None, Position.Closed]] = []
        for ss in state.symbol_states.values():
            if isinstance(ss.open_position, Position.OpenLong):
                assert ss.last_candle
                _log.info(f'{ss.symbol} long position open; closing')
                to_close.append(self._close_long_position(
                    state, ss, ss.last_candle, CloseReason.CANCELLED
                ))
            elif isinstance(ss.open_position, Position.OpenShort):
                assert ss.last_candle
                _log.info(f'{ss.symbol} short position open; closing')
                to_close.append(self._close_short_position(
                    state, ss, ss.last_candle, CloseReason.CANCELLED
                ))
        if len(to_close) > 0:
            _log.info(f'closing {len(to_close)} open position(s)')
            positions = await asyncio.gather(*to_close)
            await self._events.emit(
                config.channel, 'positions_closed', positions, state.summary
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
