import importlib
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, NamedTuple, Optional

from juno import Advice, Candle, Fill, Interval, MissedCandlePolicy, Timestamp, strategies
from juno.brokers import Broker
from juno.components import Chandler, Events, Informant
from juno.exchanges import Exchange
from juno.modules import get_module_type
from juno.strategies import Changed, Strategy
from juno.trading import Position, PositionMixin, SimulatedPositionMixin, TradingSummary
from juno.utils import tonamedtuple, unpack_symbol

from .trader import Trader

_log = logging.getLogger(__name__)


class Basic(Trader, PositionMixin, SimulatedPositionMixin):
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
        short: bool = False  # Take short positions.

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

    @dataclass
    class State:
        strategy: Optional[Strategy] = None
        changed: Optional[Changed] = None
        quote: Decimal = Decimal('-1.0')
        summary: Optional[TradingSummary] = None
        open_long_position: Optional[Position.OpenLong] = None
        open_short_position: Optional[Position.OpenShort] = None
        first_candle: Optional[Candle] = None
        last_candle: Optional[Candle] = None
        highest_close_since_position = Decimal('0.0')
        lowest_close_since_position = Decimal('Inf')
        current: Timestamp = 0
        start_adjusted: bool = False

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
        if config.short:
            assert self._informant.get_borrow_info(config.exchange, config.quote_asset)
            assert self._informant.get_fees_filters(
                config.exchange, config.symbol
            )[1].is_margin_trading_allowed

        state = state or Basic.State()

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
                        (last_candle := state.last_candle)
                        and (time_diff := (candle.time - last_candle.time)) >= config.interval * 2
                    ):
                        if config.missed_candle_policy is MissedCandlePolicy.RESTART:
                            _log.info('restarting strategy due to missed candle(s)')
                            restart = True
                            state.strategy = config.new_strategy()
                            state.current = candle.time + config.interval
                        elif config.missed_candle_policy is MissedCandlePolicy.LAST:
                            num_missed = time_diff // config.interval - 1
                            _log.info(f'filling {num_missed} missed candles with last values')
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
        await self._events.emit(config.channel, 'candle', candle)

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
            await self.open_long_position(
                candle=candle,
                exchange=config.exchange,
                symbol=config.symbol,
                test=config.test,
                quote=state.quote,
            ) if self._broker else self.open_simulated_long_position(
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
        await self._events.emit(
            config.channel, 'position_opened', state.open_long_position, state.summary
        )

    async def _close_long_position(self, config: Config, state: State, candle: Candle) -> None:
        assert state.summary
        assert state.open_long_position

        position = (
            await self.close_long_position(
                candle=candle,
                exchange=config.exchange,
                test=config.test,
                position=state.open_long_position,
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
        await self._events.emit(config.channel, 'position_closed', position, state.summary)

    async def _open_short_position(self, config: Config, state: State, candle: Candle) -> None:
        assert not state.open_long_position
        assert not state.open_short_position

        position = (
            await self.open_short_position(
                candle=candle,
                exchange=config.exchange,
                symbol=config.symbol,
                test=config.test,
                collateral=state.quote,
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
        await self._events.emit(
            config.channel, 'position_opened', state.open_short_position, state.summary
        )

    async def _close_short_position(self, config: Config, state: State, candle: Candle) -> None:
        assert state.summary
        assert state.open_short_position

        position = (
            await self.close_short_position(
                candle=candle,
                exchange=config.exchange,
                test=config.test,
                position=state.open_short_position,
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
        await self._events.emit(config.channel, 'position_closed', position, state.summary)
