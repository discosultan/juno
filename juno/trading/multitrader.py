from __future__ import annotations

import asyncio
import importlib
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, NamedTuple, Optional

from juno import Advice, Candle, Fill, Interval, Timestamp, strategies
from juno.brokers import Broker
from juno.components import Chandler, Event, Informant
from juno.exchanges import Exchange
from juno.modules import get_module_type
from juno.strategies import Changed, Strategy
from juno.utils import tonamedtuple

from .common import Position, TradingSummary
from .mixins import PositionMixin, SimulatedPositionMixin

_log = logging.getLogger(__name__)

TRACK_COUNT = 20
POSITION_COUNT = 5
SYMBOL_PATTERN = '*-btc'


@dataclass
class _SymbolState:
    strategy: Strategy
    changed: Changed
    current: Timestamp
    start_adjusted: bool = False
    open_position: Optional[Position.Open] = None
    highest_close_since_position = Decimal('0.0')
    lowest_close_since_position = Decimal('Inf')
    first_candle: Optional[Candle] = None
    last_candle: Optional[Candle] = None


class _AdviceHint(NamedTuple):
    time: Timestamp
    symbol: str
    advice: Advice


class MultiTrader(PositionMixin, SimulatedPositionMixin):
    class Config(NamedTuple):
        exchange: str
        interval: Interval
        start: Timestamp
        end: Timestamp
        quote: Decimal
        strategy: str
        strategy_module: str = strategies.__name__
        trailing_stop: Decimal = Decimal('0.0')  # 0 means disabled.
        strategy_args: List[Any] = []
        strategy_kwargs: Dict[str, Any] = {}
        channel: str = 'default'
        long: bool = True  # Take long positions.
        short: bool = False  # Also take short positions.

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

    @dataclass
    class State:
        symbol_states: Dict[str, _SymbolState] = {}
        quote: Decimal = Decimal('-1.0')
        summary: Optional[TradingSummary] = None
        advice_queue: Optional[List[_AdviceHint]] = None

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
    def informant(self) -> Informant:
        return self._informant

    @property
    def broker(self) -> Broker:
        assert self._broker
        return self._broker

    @property
    def exchanges(self) -> Dict[str, Exchange]:
        return self._exchanges

    async def run(self, config: Config, state: Optional[State] = None) -> TradingSummary:
        assert config.start >= 0
        assert config.end > 0
        assert config.end > config.start
        assert 0 <= config.trailing_stop < 1
        assert POSITION_COUNT > 0
        assert POSITION_COUNT <= TRACK_COUNT

        state = state or MultiTrader.State()

        if state.quote == -1:
            state.quote = config.quote

        if not state.summary:
            state.summary = TradingSummary(
                start=config.start,
                quote=config.quote,
                quote_asset='btc',  # TODO: support others
            )

        if len(state.symbol_states) == 0:
            symbols = self._find_top_symbols(config)
            state.symbol_states = {s: _SymbolState(
                strategy=config.new_strategy(),
                changed=Changed(True),
                current=config.start,
            ) for s in symbols}

        if state.advice_queue is None:
            state.advice_queue = []

        try:
            advice_changed = asyncio.Event()
            await asyncio.gather(
                self._manage_positions(config, state, advice_changed),
                *(self._track_advice(config, state, symbol, advice_changed)
                  for symbol in state.symbol_states.keys())
            )
        finally:
            last_candle_times = [
                s.last_candle.time for s in state.symbol_states.values() if s.last_candle
            ]
            if any(last_candle_times):
                await self._close_all_open_positions(config, state)
                state.summary.finish(max(last_candle_times) + config.interval)
            else:
                state.summary.finish(config.start)

        return state.summary

    def _find_top_symbols(self, config: Config) -> List[str]:
        tickers = self._informant.list_tickers(config.exchange, symbol_pattern=SYMBOL_PATTERN)
        if len(tickers) < TRACK_COUNT:
            raise ValueError(
                f'Exchange only support {len(tickers)} symbols matching pattern {SYMBOL_PATTERN} '
                f'while {TRACK_COUNT} requested'
            )
        return [t.symbol for t in tickers[0:TRACK_COUNT]]

    async def _manage_positions(
        self, config: Config, state: State, advice_changed: asyncio.Event
    ) -> None:
        pass

    async def _track_advice(
        self, config: Config, state: State, symbol: str, advice_changed: asyncio.Event
    ) -> None:
        symbol_state = state.symbol_states[symbol]
        if not symbol_state.start_adjusted:
            _log.info(
                f'fetching {symbol_state.strategy.adjust_hint} {symbol} candle(s) before start '
                'time to warm-up strategy'
            )
            symbol_state.current -= symbol_state.strategy.adjust_hint * config.interval
            symbol_state.start_adjusted = True

        async for candle in self._chandler.stream_candles(
            exchange=config.exchange,
            symbol=symbol,
            interval=config.interval,
            start=symbol_state.current,
            end=config.end,
            fill_missing_with_last=True,
        ):
            assert state.advice_queue is not None

            advice = symbol_state.strategy.update(candle)
            advice = symbol_state.changed.update(advice)
            _log.debug(f'received advice: {advice.name}')

            if isinstance(symbol_state.open_position, Position.OpenLong):
                if advice in [Advice.SHORT, Advice.LIQUIDATE]:
                    state.advice_queue.append(_AdviceHint(
                        time=candle.time,
                        symbol=symbol,
                        advice=advice,
                    ))
                    advice_changed.set()
                elif config.trailing_stop:
                    symbol_state.highest_close_since_position = max(
                        symbol_state.highest_close_since_position, candle.close
                    )
                    target = (
                        symbol_state.highest_close_since_position * config.upside_trailing_factor
                    )
                    if candle.close <= target:
                        _log.info(
                            f'{symbol} upside trailing stop hit at {config.trailing_stop}; selling'
                        )
                        state.advice_queue.append(_AdviceHint(
                            time=candle.time,
                            symbol=symbol,
                            advice=advice,
                        ))
                        advice_changed.set()
                        assert advice is not Advice.LONG
            elif isinstance(symbol_state.open_position, Position.OpenShort):
                if advice in [Advice.LONG, Advice.LIQUIDATE]:
                    state.advice_queue.append(_AdviceHint(
                        time=candle.time,
                        symbol=symbol,
                        advice=advice,
                    ))
                    advice_changed.set()
                elif config.trailing_stop:
                    symbol_state.lowest_close_since_position = min(
                        symbol_state.lowest_close_since_position, candle.close
                    )
                    target = (
                        symbol_state.lowest_close_since_position * config.downside_trailing_factor
                    )
                    if candle.close >= target:
                        _log.info(
                            f'{symbol} downside trailing stop hit at {config.trailing_stop}; '
                            'selling'
                        )
                        state.advice_queue.append(_AdviceHint(
                            time=candle.time,
                            symbol=symbol,
                            advice=advice,
                        ))
                        advice_changed.set()
                        assert advice is not Advice.SHORT

            if not symbol_state.open_position:
                if config.long and advice is Advice.LONG:
                    state.advice_queue.append(_AdviceHint(
                        time=candle.time,
                        symbol=symbol,
                        advice=advice,
                    ))
                    advice_changed.set()
                    symbol_state.highest_close_since_position = candle.close
                elif config.short and advice is Advice.SHORT:
                    state.advice_queue.append(_AdviceHint(
                        time=candle.time,
                        symbol=symbol,
                        advice=advice,
                    ))
                    advice_changed.set()
                    symbol_state.lowest_close_since_position = candle.close

            if not symbol_state.first_candle:
                _log.info(f'{symbol} first candle {candle}')
                symbol_state.first_candle = candle
            symbol_state.last_candle = candle
            symbol_state.current = candle.time + config.interval

    async def _close_all_open_positions(self, config: Config, state: State) -> None:
        pass

    async def _open_long_position(
        self, config: Config, state: State, candle: Candle, symbol: str
    ) -> None:
        assert not state.open_long_position
        assert not state.open_short_position

        position = (
            await self.open_long_position(
                candle=candle,
                exchange=config.exchange,
                symbol=symbol,
                quote=state.quote,
                test=False,
            ) if self._broker else self.open_simulated_long_position(
                candle=candle,
                exchange=config.exchange,
                symbol=symbol,
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

    async def _close_long_position(
        self, config: Config, state: State, candle: Candle
    ) -> None:
        assert state.summary
        assert state.open_long_position

        position = (
            await self.close_long_position(
                candle=candle,
                exchange=config.exchange,
                position=state.open_long_position,
                test=False,
            ) if self._broker else self.close_simulated_long_position(
                candle=candle,
                exchange=config.exchange,
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

    async def _open_short_position(
        self, config: Config, state: State, candle: Candle, symbol: str
    ) -> None:
        assert not state.open_long_position
        assert not state.open_short_position

        position = (
            await self.open_short_position(
                candle=candle,
                exchange=config.exchange,
                symbol=symbol,
                collateral=state.quote,
                test=False,
            ) if self._broker else self.open_simulated_short_position(
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

    async def _close_short_position(
        self, config: Config, state: State, candle: Candle
    ) -> None:
        assert state.summary
        assert state.open_short_position

        position = (
            await self.close_short_position(
                candle=candle,
                exchange=config.exchange,
                position=state.open_short_position,
                test=False,
            ) if self._broker else self.close_simulated_short_position(
                candle=candle,
                exchange=config.exchange,
                position=state.open_short_position,
            )
        )

        state.quote -= Fill.total_quote(position.close_fills)
        state.open_short_position = None
        state.summary.append_position(position)

        _log.info(f'short position closed: {candle}')
        _log.debug(tonamedtuple(position))
        await self._event.emit(config.channel, 'position_closed', position, state.summary)
