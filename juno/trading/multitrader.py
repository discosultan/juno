from __future__ import annotations

import asyncio
import importlib
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Coroutine, Dict, List, NamedTuple, Optional

from juno import Advice, Candle, Fill, Interval, Timestamp, strategies
from juno.asyncio import SlotBarrier
from juno.brokers import Broker
from juno.components import Chandler, Events, Informant
from juno.exchanges import Exchange
from juno.math import split_by_ratios
from juno.modules import get_module_type
from juno.strategies import Changed, Strategy
from juno.utils import tonamedtuple

from .common import Position, TradingSummary
from .mixins import PositionMixin, SimulatedPositionMixin

_log = logging.getLogger(__name__)

TRACK_COUNT = 4
POSITION_COUNT = 2
SYMBOL_PATTERN = '*-btc'


@dataclass
class _SymbolState:
    strategy: Strategy
    changed: Changed
    current: Timestamp
    quote: Decimal
    start_adjusted: bool = False
    open_position: Optional[Position.Open] = None
    highest_close_since_position = Decimal('0.0')
    lowest_close_since_position = Decimal('Inf')
    first_candle: Optional[Candle] = None
    last_candle: Optional[Candle] = None


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
        short: bool = False  # Take short positions.

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
        summary: Optional[TradingSummary] = None

    def __init__(
        self,
        chandler: Chandler,
        informant: Informant,
        broker: Optional[Broker] = None,
        events: Events = Events(),
        exchanges: List[Exchange] = [],
    ) -> None:
        self._chandler = chandler
        self._informant = informant
        self._broker = broker
        self._events = events
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

        if not state.summary:
            state.summary = TradingSummary(
                start=config.start,
                quote=config.quote,
                quote_asset='btc',  # TODO: support others
            )

        if len(state.symbol_states) == 0:
            ratio = Decimal('1.0') / POSITION_COUNT
            quotes = split_by_ratios(config.quote, [ratio] * POSITION_COUNT)
            symbols = self._find_top_symbols(config)
            state.symbol_states = {s: _SymbolState(
                strategy=config.new_strategy(),
                changed=Changed(True),
                current=config.start,
                quote=q,
            ) for s, q in zip(symbols, quotes)}

        _log.info(
            f'managing up to {POSITION_COUNT} positions by tracking top {TRACK_COUNT} symbols: '
            f'{symbols}'
        )

        try:
            candles_updated = SlotBarrier(symbols)
            await asyncio.gather(
                self._manage_positions(config, state, candles_updated),
                *(self._track_advice(config, state, symbol, candles_updated)
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
        self, config: Config, state: State, candles_updated: SlotBarrier
    ) -> None:
        to_close: List[Coroutine[None, None, None]] = []
        to_open: List[Coroutine[None, None, Position.Open]] = []
        while True:
            # Wait until we've received candle updates for all symbols.
            await candles_updated.wait()

            # Try close existing positions.
            to_close.clear()
            for ss in state.symbol_states.values():
                assert ss.last_candle
                if (
                    isinstance(ss.open_position, Position.OpenLong)
                    and ss.changed.prevailing_advice in [Advice.LIQUIDATE, Advice.SHORT]
                ):
                    to_close.append(self._close_long_position(
                        config, state, ss.open_position, ss.last_candle
                    ))
                    ss.open_position = None
                elif (
                    isinstance(ss.open_position, Position.OpenShort)
                    and ss.changed.prevailing_advice in [Advice.LIQUIDATE, Advice.LONG]
                ):
                    to_close.append(self._close_short_position(
                        config, state, ss.open_position, ss.last_candle
                    ))
                    ss.open_position = None
            if len(to_close) > 0:
                await asyncio.gather(*to_close)

            # Try open new positions.
            to_open.clear()
            count = sum(1 for ss in state.symbol_states.values() if ss.open_position is not None)
            assert count <= POSITION_COUNT
            available = POSITION_COUNT - count
            for symbol, ss in state.symbol_states.items():
                if available == 0:
                    break

                if ss.open_position:
                    continue

                assert ss.last_candle
                if (
                    ss.changed.prevailing_advice is Advice.LONG
                    and ss.changed.prevailing_advice_age == 1  # TODO: Be more flexible?
                ):
                    to_open.append(self._open_long_position(
                        config, state, ss.last_candle, symbol
                    ))
                    available -= 1
                elif (
                    ss.changed.prevailing_advice is Advice.SHORT
                    and ss.changed.prevailing_advice_age == 1
                ):
                    to_open.append(self._open_short_position(
                        config, state, ss.last_candle, symbol
                    ))
                    available -= 1
            if len(to_open) > 0:
                positions = await asyncio.gather(*to_open)
                for pos in positions:
                    state.symbol_states[pos.symbol].open_position = pos

            # Clear barrier for next update.
            candles_updated.clear()

    async def _track_advice(
        self, config: Config, state: State, symbol: str, candles_updated: SlotBarrier
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
            advice = symbol_state.strategy.update(candle)
            _log.debug(f'received advice: {advice.name}')

            if (
                isinstance(symbol_state.open_position, Position.OpenLong)
                and advice not in [Advice.SHORT, Advice.LIQUIDATE]
                and config.trailing_stop
            ):
                assert advice is not Advice.LONG
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
                    advice = Advice.LIQUIDATE
            elif (
                isinstance(symbol_state.open_position, Position.OpenShort)
                and advice not in [Advice.LONG, Advice.LIQUIDATE]
                and config.trailing_stop
            ):
                assert advice is not Advice.SHORT
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
                    advice = Advice.LIQUIDATE

            if not symbol_state.open_position:
                if config.long and advice is Advice.LONG:
                    symbol_state.highest_close_since_position = candle.close
                elif config.short and advice is Advice.SHORT:
                    symbol_state.lowest_close_since_position = candle.close

            symbol_state.changed.update(advice)

            if not symbol_state.first_candle:
                _log.info(f'{symbol} first candle {candle}')
                symbol_state.first_candle = candle
            symbol_state.last_candle = candle
            symbol_state.current = candle.time + config.interval

            candles_updated.release(symbol)

    async def _close_all_open_positions(self, config: Config, state: State) -> None:
        to_close = []
        for ss in state.symbol_states.values():
            assert ss.last_candle
            if isinstance(ss.open_position, Position.OpenLong):
                to_close.append(self._close_long_position(
                    config, state, ss.open_position, ss.last_candle
                ))
            elif isinstance(ss.open_position, Position.OpenShort):
                to_close.append(self._close_short_position(
                    config, state, ss.open_position, ss.last_candle
                ))
        if len(to_close) > 0:
            await asyncio.gather(*to_close)

    async def _open_long_position(
        self, config: Config, state: State, candle: Candle, symbol: str
    ) -> Position.OpenLong:
        symbol_state = state.symbol_states[symbol]

        position = (
            await self.open_long_position(
                candle=candle,
                exchange=config.exchange,
                symbol=symbol,
                quote=symbol_state.quote,
                test=False,
            ) if self._broker else self.open_simulated_long_position(
                candle=candle,
                exchange=config.exchange,
                symbol=symbol,
                quote=symbol_state.quote,
            )
        )

        symbol_state.quote -= Fill.total_quote(position.fills)

        _log.info(f'long position opened: {candle}')
        _log.debug(tonamedtuple(position))
        await self._events.emit(
            config.channel, 'position_opened', position, state.summary
        )
        return position

    async def _close_long_position(
        self, config: Config, state: State, open_position: Position.OpenLong, candle: Candle
    ) -> None:
        assert state.summary
        symbol_state = state.symbol_states[open_position.symbol]

        position = (
            await self.close_long_position(
                candle=candle,
                exchange=config.exchange,
                position=open_position,
                test=False,
            ) if self._broker else self.close_simulated_long_position(
                candle=candle,
                exchange=config.exchange,
                position=open_position,
            )
        )

        symbol_state.quote += (
            Fill.total_quote(position.close_fills) - Fill.total_fee(position.close_fills)
        )
        state.summary.append_position(position)

        _log.info(f'{position.symbol} long position closed: {candle}')
        _log.debug(tonamedtuple(position))
        await self._events.emit(config.channel, 'position_closed', position, state.summary)

    async def _open_short_position(
        self, config: Config, state: State, candle: Candle, symbol: str
    ) -> Position.OpenShort:
        symbol_state = state.symbol_states[symbol]

        position = (
            await self.open_short_position(
                candle=candle,
                exchange=config.exchange,
                symbol=symbol,
                collateral=symbol_state.quote,
                test=False,
            ) if self._broker else self.open_simulated_short_position(
                candle=candle,
                exchange=config.exchange,
                symbol=symbol,
                collateral=symbol_state.quote,
            )
        )

        symbol_state.quote += Fill.total_quote(position.fills) - Fill.total_fee(position.fills)

        _log.info(f'short position opened: {candle}')
        _log.debug(tonamedtuple(position))
        await self._events.emit(
            config.channel, 'position_opened', position, state.summary
        )
        return position

    async def _close_short_position(
        self, config: Config, state: State, open_position: Position.OpenShort, candle: Candle
    ) -> None:
        assert state.summary
        symbol_state = state.symbol_states[open_position.symbol]

        position = (
            await self.close_short_position(
                candle=candle,
                exchange=config.exchange,
                position=open_position,
                test=False,
            ) if self._broker else self.close_simulated_short_position(
                candle=candle,
                exchange=config.exchange,
                position=open_position,
            )
        )

        symbol_state.quote -= Fill.total_quote(position.close_fills)
        state.summary.append_position(position)

        _log.info(f'{position.symbol} short position closed: {candle}')
        _log.debug(tonamedtuple(position))
        await self._events.emit(config.channel, 'position_closed', position, state.summary)
