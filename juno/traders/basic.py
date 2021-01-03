import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Type

from juno import Advice, Candle, Interval, MissedCandlePolicy, Timestamp
from juno.brokers import Broker
from juno.components import Chandler, Events, Informant, User
from juno.exchanges import Exchange
from juno.stop_loss import Noop as NoopStopLoss
from juno.stop_loss import StopLoss
from juno.strategies import Changed, Signal
from juno.take_profit import Noop as NoopTakeProfit
from juno.take_profit import TakeProfit
from juno.time import time_ms
from juno.trading import (
    CloseReason, Position, PositionMixin, SimulatedPositionMixin, StartMixin, TradingMode,
    TradingSummary
)
from juno.typing import TypeConstructor
from juno.utils import unpack_symbol

from .trader import Trader

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class BasicConfig:
    exchange: str
    symbol: str
    interval: Interval
    end: Timestamp
    strategy: TypeConstructor[Signal]
    stop_loss: Optional[TypeConstructor[StopLoss]] = None
    take_profit: Optional[TypeConstructor[TakeProfit]] = None
    start: Optional[Timestamp] = None  # None means earliest is found.
    quote: Optional[Decimal] = None  # None means exchange wallet is queried.
    mode: TradingMode = TradingMode.BACKTEST
    channel: str = 'default'
    missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE
    adjust_start: bool = True
    long: bool = True  # Take long positions.
    short: bool = False  # Take short positions.
    close_on_exit: bool = True  # Whether to close open position on exit.
    # Timeout in case no candle (including open) from exchange.
    exchange_candle_timeout: Optional[Interval] = None

    @property
    def base_asset(self) -> str:
        return unpack_symbol(self.symbol)[0]

    @property
    def quote_asset(self) -> str:
        return unpack_symbol(self.symbol)[1]


@dataclass
class BasicState:
    config: BasicConfig
    close_on_exit: bool

    strategy: Signal
    quote: Decimal
    summary: TradingSummary
    current: Timestamp  # Candle time.
    start: Timestamp  # Candle time.
    real_start: Timestamp
    stop_loss: StopLoss
    take_profit: TakeProfit

    changed: Changed = field(default_factory=lambda: Changed(True))
    open_new_positions: bool = True  # Whether new positions can be opened.
    open_position: Optional[Position.Open] = None
    first_candle: Optional[Candle] = None
    last_candle: Optional[Candle] = None

    @property
    def open_positions(self) -> List[Position.Open]:
        return [self.open_position] if self.open_position else []


class Basic(Trader[BasicConfig, BasicState], PositionMixin, SimulatedPositionMixin, StartMixin):
    @staticmethod
    def config() -> Type[BasicConfig]:
        return BasicConfig

    @staticmethod
    def state() -> Type[BasicState]:
        return BasicState

    def __init__(
        self,
        chandler: Chandler,
        informant: Informant,
        user: Optional[User] = None,
        broker: Optional[Broker] = None,  # Only required if not backtesting.
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

    async def initialize(self, config: BasicConfig) -> BasicState:
        assert config.mode is TradingMode.BACKTEST or self.broker
        assert config.start is None or config.start >= 0
        assert config.end > 0
        assert config.start is None or config.end > config.start

        _, filters = self._informant.get_fees_filters(config.exchange, config.symbol)
        assert filters.spot
        if config.short:
            assert filters.isolated_margin

        start = await self.request_start(
            config.start, config.exchange, [config.symbol], [config.interval]
        )
        quote = await self.request_quote(
            config.quote, config.exchange, config.quote_asset, config.mode
        )
        assert quote > filters.price.min

        strategy = config.strategy.construct()

        current = start
        if config.adjust_start:
            # Adjust start to accommodate for the required history before a strategy
            # becomes effective. Only do it on first run because subsequent runs mean
            # missed candles and we don't want to fetch passed a missed candle.
            _log.info(
                f'fetching {strategy.maturity - 1} candle(s) before start time to warm-up '
                'strategy'
            )
            current = max(current - (strategy.maturity - 1) * config.interval, 0)

        return BasicState(
            config=config,
            close_on_exit=config.close_on_exit,
            start=start,
            real_start=self._get_time_ms(),
            quote=quote,
            summary=TradingSummary(
                start=start,
                quote=quote,
                quote_asset=config.quote_asset,
            ),
            strategy=strategy,
            current=current,
            stop_loss=(
                NoopStopLoss() if config.stop_loss is None else config.stop_loss.construct()
            ),
            take_profit=(
                NoopTakeProfit() if config.take_profit is None
                else config.take_profit.construct()
            ),
        )

    async def run(self, state: BasicState) -> TradingSummary:
        config = state.config
        try:
            async for candle in self._chandler.stream_candles(
                exchange=config.exchange,
                symbol=config.symbol,
                interval=config.interval,
                start=state.current,
                end=config.end,
                exchange_timeout=config.exchange_candle_timeout,
            ):
                # Check if we have missed a candle.
                if (
                    (last_candle := state.last_candle)
                    and (time_diff := (candle.time - last_candle.time)) >= config.interval * 2
                ):
                    if config.missed_candle_policy is MissedCandlePolicy.RESTART:
                        _log.info('restarting strategy due to missed candle(s)')
                        # restart = True
                        state.strategy = config.strategy.construct()
                        state.current = candle.time + config.interval
                    elif config.missed_candle_policy is MissedCandlePolicy.LAST:
                        num_missed = time_diff // config.interval - 1
                        _log.info(f'filling {num_missed} missed candles with last values')
                        for i in range(1, num_missed + 1):
                            missed_candle = Candle(
                                time=last_candle.time + i * config.interval,
                                open=last_candle.close,
                                high=last_candle.close,
                                low=last_candle.close,
                                close=last_candle.close,
                                volume=Decimal('0.0'),
                                closed=True,
                            )
                            await self._tick(state, missed_candle)

                await self._tick(state, candle)
        finally:
            if state.close_on_exit:
                await self._close_open_position(state)
            if config.end is not None and config.end <= state.real_start:  # Backtest.
                end = (
                    state.last_candle.time + config.interval if state.last_candle
                    else state.summary.start + config.interval
                )
            else:  # Paper or live.
                end = min(self._get_time_ms(), config.end)
            state.summary.finish(end)
            if state.last_candle:
                _log.info(f'last candle: {state.last_candle}')

        _log.info('finished')
        return state.summary

    async def _tick(self, state: BasicState, candle: Candle) -> None:
        config = state.config
        await self._events.emit(config.channel, 'candle', candle)

        assert state.strategy
        assert state.changed
        assert state.summary
        state.stop_loss.update(candle)
        state.take_profit.update(candle)
        state.strategy.update(candle)
        advice = state.changed.update(state.strategy.advice)
        _log.debug(f'received advice: {advice.name}')
        # Make sure strategy doesn't give advice during "adjusted start" period.
        if state.current < state.summary.start:
            assert advice is Advice.NONE

        if isinstance(state.open_position, Position.OpenLong):
            if advice in [Advice.SHORT, Advice.LIQUIDATE]:
                await self._close_long_position(state, candle, CloseReason.STRATEGY)
            elif state.open_position and state.stop_loss.upside_hit:
                _log.info(f'upside stop loss hit at {config.stop_loss}; selling')
                await self._close_long_position(state, candle, CloseReason.STOP_LOSS)
                assert advice is not Advice.LONG
            elif state.open_position and state.take_profit.upside_hit:
                _log.info(f'upside take profit hit at {config.take_profit}; selling')
                await self._close_long_position(state, candle, CloseReason.TAKE_PROFIT)
                assert advice is not Advice.LONG

        elif isinstance(state.open_position, Position.OpenShort):
            if advice in [Advice.LONG, Advice.LIQUIDATE]:
                await self._close_short_position(state, candle, CloseReason.STRATEGY)
            elif state.stop_loss.downside_hit:
                _log.info(f'downside stop loss hit at {config.stop_loss}; selling')
                await self._close_short_position(state, candle, CloseReason.STOP_LOSS)
                assert advice is not Advice.SHORT
            elif state.take_profit.downside_hit:
                _log.info(f'downside take profit hit at {config.take_profit}; selling')
                await self._close_short_position(state, candle, CloseReason.TAKE_PROFIT)
                assert advice is not Advice.SHORT

        if not state.open_position and state.open_new_positions:
            if config.long and advice is Advice.LONG:
                await self._open_long_position(state, candle)
            elif config.short and advice is Advice.SHORT:
                await self._open_short_position(state, candle)
            state.stop_loss.clear(candle)
            state.take_profit.clear(candle)

        if not state.first_candle:
            _log.info(f'first candle: {candle}')
            state.first_candle = candle
        state.last_candle = candle
        state.current = candle.time + config.interval

    async def _close_open_position(self, state: BasicState) -> None:
        if isinstance(state.open_position, Position.OpenLong):
            assert state.last_candle
            _log.info(f'{state.open_position.symbol} long position open; closing')
            await self._close_long_position(state, state.last_candle, CloseReason.CANCELLED)
        elif isinstance(state.open_position, Position.OpenShort):
            assert state.last_candle
            _log.info(f'{state.open_position.symbol} short position open; closing')
            await self._close_short_position(state, state.last_candle, CloseReason.CANCELLED)

    async def _open_long_position(self, state: BasicState, candle: Candle) -> None:
        config = state.config
        assert not state.open_position

        position = (
            self.open_simulated_long_position(
                exchange=config.exchange,
                symbol=config.symbol,
                time=candle.time + config.interval,
                price=candle.close,
                quote=state.quote,
            )
            if config.mode is TradingMode.BACKTEST else
            await self.open_long_position(
                exchange=config.exchange,
                symbol=config.symbol,
                quote=state.quote,
                mode=config.mode,
            )
        )

        state.quote += position.quote_delta()
        state.open_position = position

        await self._events.emit(
            config.channel, 'positions_opened', [state.open_position], state.summary
        )

    async def _close_long_position(
        self, state: BasicState, candle: Candle, reason: CloseReason
    ) -> None:
        config = state.config
        assert state.summary
        assert isinstance(state.open_position, Position.OpenLong)

        position = (
            self.close_simulated_long_position(
                position=state.open_position,
                time=candle.time + config.interval,
                price=candle.close,
                reason=reason,
            )
            if config.mode is TradingMode.BACKTEST else
            await self.close_long_position(
                position=state.open_position,
                mode=config.mode,
                reason=reason,
            )
        )

        state.quote += position.quote_delta()
        state.open_position = None
        state.summary.append_position(position)

        await self._events.emit(config.channel, 'positions_closed', [position], state.summary)

    async def _open_short_position(self, state: BasicState, candle: Candle) -> None:
        config = state.config
        assert not state.open_position

        position = (
            self.open_simulated_short_position(
                exchange=config.exchange,
                symbol=config.symbol,
                time=candle.time + config.interval,
                price=candle.close,
                collateral=state.quote,
            )
            if config.mode is TradingMode.BACKTEST else
            await self.open_short_position(
                exchange=config.exchange,
                symbol=config.symbol,
                collateral=state.quote,
                mode=config.mode,
            )
        )

        state.quote += position.quote_delta()
        state.open_position = position

        await self._events.emit(
            config.channel, 'positions_opened', [state.open_position], state.summary
        )

    async def _close_short_position(
        self, state: BasicState, candle: Candle, reason: CloseReason
    ) -> None:
        config = state.config
        assert state.summary
        assert isinstance(state.open_position, Position.OpenShort)

        position = (
            self.close_simulated_short_position(
                position=state.open_position,
                time=candle.time + config.interval,
                price=candle.close,
                reason=reason,
            )
            if config.mode is TradingMode.BACKTEST else
            await self.close_short_position(
                position=state.open_position,
                mode=config.mode,
                reason=reason,
            )
        )

        state.quote += position.quote_delta()
        state.open_position = None
        state.summary.append_position(position)

        await self._events.emit(config.channel, 'positions_closed', [position], state.summary)
