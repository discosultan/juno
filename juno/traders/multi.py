from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Coroutine, Dict, List, NamedTuple, Optional, Tuple

from juno import Advice, Candle, Fill, Interval, Timestamp
from juno.asyncio import Event, SlotBarrier
from juno.brokers import Broker
from juno.components import Chandler, Events, Informant, Wallet
from juno.exchanges import Exchange
from juno.math import floor_multiple
from juno.strategies import Changed, Strategy
from juno.time import strftimestamp, time_ms
from juno.trading import (
    CloseReason, Position, PositionMixin, SimulatedPositionMixin, StartMixin, TradingSummary
)
from juno.typing import TypeConstructor
from juno.utils import extract_public

from .trader import Trader

_log = logging.getLogger(__name__)

SYMBOL_PATTERN = '*-btc'


@dataclass
class _SymbolState:
    symbol: str
    strategy: Strategy
    changed: Changed
    override_changed: Changed
    current: Timestamp
    start_adjusted: bool = False
    open_position: Optional[Position.Open] = None
    allocated_quote: Decimal = Decimal('0.0')
    highest_close_since_position = Decimal('0.0')
    lowest_close_since_position = Decimal('Inf')
    first_candle: Optional[Candle] = None
    last_candle: Optional[Candle] = None

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
        return (
            CloseReason.STRATEGY if self.override_changed.prevailing_advice is Advice.NONE
            else CloseReason.TRAILING_STOP
        )


class Multi(Trader, PositionMixin, SimulatedPositionMixin, StartMixin):
    class Config(NamedTuple):
        exchange: str
        interval: Interval
        end: Timestamp
        strategy: TypeConstructor[Strategy]
        symbol_strategies: Dict[str, TypeConstructor[Strategy]] = {}  # Overrides default strategy.
        start: Optional[Timestamp] = None  # None means max earliest is found.
        quote: Optional[Decimal] = None  # None means exchange wallet is queried.
        trailing_stop: Decimal = Decimal('0.0')  # 0 means disabled.
        adjust_start: bool = True
        test: bool = True  # No effect if broker is None.
        channel: str = 'default'
        long: bool = True  # Take long positions.
        short: bool = False  # Take short positions.
        track: List[str] = []
        track_count: int = 4
        track_required_start: Optional[Timestamp] = None
        position_count: int = 2

        @property
        def upside_trailing_factor(self) -> Decimal:
            return 1 - self.trailing_stop

        @property
        def downside_trailing_factor(self) -> Decimal:
            return 1 + self.trailing_stop

    @dataclass
    class State:
        start: Timestamp = -1
        symbol_states: Dict[str, _SymbolState] = field(default_factory=dict)
        quotes: List[Decimal] = field(default_factory=list)
        summary: Optional[TradingSummary] = None
        real_start: Timestamp = -1

    def __init__(
        self,
        chandler: Chandler,
        informant: Informant,
        wallet: Optional[Wallet] = None,
        broker: Optional[Broker] = None,
        events: Events = Events(),
        exchanges: List[Exchange] = [],
        get_time_ms: Callable[[], int] = time_ms,
    ) -> None:
        self._chandler = chandler
        self._informant = informant
        self._wallet = wallet
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
    def wallet(self) -> Wallet:
        assert self._wallet
        return self._wallet

    async def run(self, config: Config, state: Optional[State] = None) -> TradingSummary:
        assert config.start is None or config.start >= 0
        assert config.end > 0
        assert config.start is None or config.end > config.start
        assert 0 <= config.trailing_stop < 1
        assert config.position_count > 0
        assert config.position_count <= config.track_count
        assert len(config.track) <= config.track_count

        symbols = await self._find_top_symbols(config)

        # Request and assert available quote.
        quote = self.request_quote(config.quote, config.exchange, 'btc', config.test)
        position_quote = quote / config.position_count
        for symbol in symbols:
            fees, filters = self._informant.get_fees_filters(config.exchange, symbol)
            assert position_quote > filters.price.min

        # Request start.
        start = await self.request_start(config.start, config.exchange, symbols, [config.interval])

        state = state or Multi.State()

        if state.real_start == -1:
            state.real_start = self._get_time_ms()

        if state.start == -1:
            state.start = start

        if not state.summary:
            state.summary = TradingSummary(
                start=start,
                quote=quote,
                quote_asset='btc',  # TODO: support others
            )
            state.quotes = [quote / config.position_count] * config.position_count
            _log.info(f'quote split as: {state.quotes}')

        if len(state.symbol_states) == 0:
            for s in symbols:
                state.symbol_states[s] = _SymbolState(
                    symbol=s,
                    strategy=config.symbol_strategies.get(s, config.strategy).construct(),
                    changed=Changed(True),
                    override_changed=Changed(True),
                    current=start,
                )

        _log.info(
            f'managing up to {config.position_count} positions by tracking top '
            f'{config.track_count} symbols: {list(state.symbol_states.keys())}'
        )

        try:
            candles_updated = SlotBarrier(state.symbol_states.keys())
            trackers_ready: Dict[str, Event] = {
                s: Event(autoclear=True) for s in state.symbol_states.keys()
            }
            await asyncio.gather(
                self._manage_positions(config, state, candles_updated, trackers_ready),
                *(self._track_advice(config, state, ss, candles_updated, trackers_ready[s])
                  for s, ss in state.symbol_states.items())
            )
        finally:
            await self._close_all_open_positions(config, state)
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

    async def _find_top_symbols(self, config: Config) -> List[str]:
        count = config.track_count - len(config.track)
        tickers = self._informant.list_tickers(
            config.exchange, symbol_pattern=SYMBOL_PATTERN, short=config.short
        )
        if config.track_required_start is not None:
            first_candles = await asyncio.gather(
                *(
                    self._chandler.get_first_candle(config.exchange, t.symbol, config.interval)
                    for t in tickers
                )
            )
            tickers = [
                t for t, c in zip(tickers, first_candles) if c.time <= config.track_required_start
            ]
        if len(tickers) < config.track_count:
            raise ValueError(
                f'Exchange only support {len(tickers)} symbols matching pattern {SYMBOL_PATTERN} '
                f'while {config.track_count} requested; required start: '
                f'{strftimestamp(config.track_required_start)}'
            )
        return config.track + [t.symbol for t in tickers[0:count] if t not in config.track]

    async def _manage_positions(
        self, config: Config, state: State, candles_updated: SlotBarrier,
        trackers_ready: Dict[str, Event]
    ) -> None:
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
                        self._close_long_position(config, state, ss, ss.last_candle, ss.reason)
                    )
                elif (
                    isinstance(ss.open_position, Position.OpenShort)
                    and ss.advice in [Advice.LIQUIDATE, Advice.LONG]
                ):
                    to_process.append(
                        self._close_short_position(config, state, ss, ss.last_candle, ss.reason)
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
            for ss in (ss for ss in state.symbol_states.values() if ss.ready):
                if available == 0:
                    break

                if ss.open_position:
                    continue

                assert ss.last_candle
                # TODO: Be more flexible?
                if ss.advice is Advice.LONG and ss.advice_age == 1:
                    to_process.append(self._open_long_position(config, state, ss, ss.last_candle))
                    available -= 1
                elif ss.advice is Advice.SHORT and ss.advice_age == 1:
                    to_process.append(self._open_short_position(config, state, ss, ss.last_candle))
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
                break

    async def _track_advice(
        self, config: Config, state: State, symbol_state: _SymbolState,
        candles_updated: SlotBarrier, ready: Event
    ) -> None:
        if config.adjust_start and not symbol_state.start_adjusted:
            _log.info(
                f'fetching {symbol_state.strategy.adjust_hint} {symbol_state.symbol} candle(s) '
                'before start time to warm-up strategy'
            )
            symbol_state.current -= symbol_state.strategy.adjust_hint * config.interval
            symbol_state.start_adjusted = True

        async for candle in self._chandler.stream_candles(
            exchange=config.exchange,
            symbol=symbol_state.symbol,
            interval=config.interval,
            start=symbol_state.current,
            end=config.end,
            fill_missing_with_last=True,
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
                        symbol_state, candles_updated, ready, Advice.NONE, Advice.NONE
                    )

            advice, override_advice = self._process_candle(config, symbol_state, candle)
            await self._process_advice(
                symbol_state, candles_updated, ready, advice, override_advice
            )

    def _process_candle(
        self, config: Config, symbol_state: _SymbolState, candle: Candle
    ) -> Tuple[Advice, Advice]:
        advice = symbol_state.strategy.update(candle)
        override_advice = Advice.NONE
        if (
            isinstance(symbol_state.open_position, Position.OpenLong)
            and advice not in [Advice.SHORT, Advice.LIQUIDATE]
            and config.trailing_stop
        ):
            assert candle
            symbol_state.highest_close_since_position = max(
                symbol_state.highest_close_since_position, candle.close
            )
            target = (
                symbol_state.highest_close_since_position * config.upside_trailing_factor
            )
            if candle.close <= target:
                _log.info(
                    f'{symbol_state.symbol} upside trailing stop hit at {config.trailing_stop}; '
                    'selling'
                )
                override_advice = Advice.LIQUIDATE
        elif (
            isinstance(symbol_state.open_position, Position.OpenShort)
            and advice not in [Advice.LONG, Advice.LIQUIDATE]
            and config.trailing_stop
        ):
            assert candle
            symbol_state.lowest_close_since_position = min(
                symbol_state.lowest_close_since_position, candle.close
            )
            target = (
                symbol_state.lowest_close_since_position * config.downside_trailing_factor
            )
            if candle.close >= target:
                _log.info(
                    f'{symbol_state.symbol} downside trailing stop hit at {config.trailing_stop}; '
                    'selling'
                )
                override_advice = Advice.LIQUIDATE

        if not symbol_state.open_position:
            if config.long and advice is Advice.LONG:
                symbol_state.highest_close_since_position = candle.close
            elif config.short and advice is Advice.SHORT:
                symbol_state.lowest_close_since_position = candle.close

        if not symbol_state.first_candle:
            _log.info(f'{symbol_state.symbol} first candle {candle}')
            symbol_state.first_candle = candle
        symbol_state.last_candle = candle
        symbol_state.current = candle.time + config.interval

        return advice, override_advice

    async def _process_advice(
        self, symbol_state: _SymbolState, candles_updated: SlotBarrier, ready: Event,
        advice: Advice, override_advice: Advice
    ) -> None:
        _log.debug(f'{symbol_state.symbol} received advice: {advice.name} {override_advice.name}')

        if override_advice is not Advice.NONE:
            symbol_state.override_changed.update(override_advice)
        elif advice is not symbol_state.changed.prevailing_advice:
            symbol_state.override_changed.update(Advice.NONE)
        else:
            symbol_state.override_changed.update(symbol_state.override_changed.prevailing_advice)

        symbol_state.changed.update(advice)

        candles_updated.release(symbol_state.symbol)
        await ready.wait()

    async def _close_all_open_positions(self, config: Config, state: State) -> None:
        to_close: List[Coroutine[None, None, Position.Closed]] = []
        for ss in state.symbol_states.values():
            if isinstance(ss.open_position, Position.OpenLong):
                assert ss.last_candle
                _log.info(f'{ss.symbol} long position open; closing')
                to_close.append(self._close_long_position(
                    config, state, ss, ss.last_candle, CloseReason.CANCELLED
                ))
            elif isinstance(ss.open_position, Position.OpenShort):
                assert ss.last_candle
                _log.info(f'{ss.symbol} short position open; closing')
                to_close.append(self._close_short_position(
                    config, state, ss, ss.last_candle, CloseReason.CANCELLED
                ))
        if len(to_close) > 0:
            _log.info(f'closing {len(to_close)} open position(s)')
            positions = await asyncio.gather(*to_close)
            await self._events.emit(
                config.channel, 'positions_closed', positions, state.summary
            )

    async def _open_long_position(
        self, config: Config, state: State, symbol_state: _SymbolState, candle: Candle
    ) -> Position.OpenLong:
        symbol_state.allocated_quote = state.quotes.pop(0)

        position = (
            await self.open_long_position(
                exchange=config.exchange,
                symbol=symbol_state.symbol,
                quote=symbol_state.allocated_quote,
                test=config.test,
            ) if self._broker else self.open_simulated_long_position(
                exchange=config.exchange,
                symbol=symbol_state.symbol,
                time=candle.time + config.interval,
                price=candle.close,
                quote=symbol_state.allocated_quote,
            )
        )

        symbol_state.allocated_quote -= Fill.total_quote(position.fills)
        symbol_state.open_position = position

        _log.info(f'{symbol_state.symbol} long position opened: {candle}')
        _log.debug(extract_public(position))
        return position

    async def _close_long_position(
        self, config: Config, state: State, symbol_state: _SymbolState, candle: Candle,
        reason: CloseReason
    ) -> Position.Long:
        assert state.summary
        assert isinstance(symbol_state.open_position, Position.OpenLong)

        position = (
            await self.close_long_position(
                position=symbol_state.open_position,
                test=config.test,
                reason=reason,
            ) if self._broker else self.close_simulated_long_position(
                position=symbol_state.open_position,
                time=candle.time + config.interval,
                price=candle.close,
                reason=reason,
            )
        )

        symbol_state.allocated_quote += (
            Fill.total_quote(position.close_fills) - Fill.total_fee(position.close_fills)
        )
        state.quotes.append(symbol_state.allocated_quote)
        symbol_state.allocated_quote = Decimal('0.0')

        state.summary.append_position(position)
        symbol_state.open_position = None

        _log.info(f'{position.symbol} long position closed: {candle}')
        _log.debug(extract_public(position))
        return position

    async def _open_short_position(
        self, config: Config, state: State, symbol_state: _SymbolState, candle: Candle
    ) -> Position.OpenShort:
        symbol_state.allocated_quote = state.quotes.pop(0)

        position = (
            await self.open_short_position(
                exchange=config.exchange,
                symbol=symbol_state.symbol,
                price=candle.close,
                collateral=symbol_state.allocated_quote,
                test=config.test,
            ) if self._broker else self.open_simulated_short_position(
                exchange=config.exchange,
                symbol=symbol_state.symbol,
                time=candle.time + config.interval,
                price=candle.close,
                collateral=symbol_state.allocated_quote,
            )
        )

        symbol_state.allocated_quote += (
            Fill.total_quote(position.fills) - Fill.total_fee(position.fills)
        )
        symbol_state.open_position = position

        _log.info(f'{symbol_state.symbol} short position opened: {candle}')
        _log.debug(extract_public(position))
        return position

    async def _close_short_position(
        self, config: Config, state: State, symbol_state: _SymbolState, candle: Candle,
        reason: CloseReason
    ) -> Position.Short:
        assert state.summary
        assert isinstance(symbol_state.open_position, Position.OpenShort)

        position = (
            await self.close_short_position(
                position=symbol_state.open_position,
                price=candle.close,
                test=config.test,
                reason=reason,
            ) if self._broker else self.close_simulated_short_position(
                position=symbol_state.open_position,
                time=candle.time + config.interval,
                price=candle.close,
                reason=reason,
            )
        )

        symbol_state.allocated_quote -= Fill.total_quote(position.close_fills)
        state.quotes.append(symbol_state.allocated_quote)
        symbol_state.allocated_quote = Decimal('0.0')

        state.summary.append_position(position)
        symbol_state.open_position = None

        _log.info(f'{position.symbol} short position closed: {candle}')
        _log.debug(extract_public(position))
        return position
