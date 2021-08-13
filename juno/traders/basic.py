import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Awaitable, Callable, Optional, TypeVar, Union
from uuid import uuid4

from juno import Advice, Candle, Interval, MissedCandlePolicy, Timestamp
from juno.asyncio import process_task_on_queue
from juno.brokers import Broker
from juno.components import Chandler, Events, Informant, User
from juno.custodians import Custodian, Stub
from juno.stop_loss import Noop as NoopStopLoss
from juno.stop_loss import StopLoss
from juno.strategies import Changed, Signal
from juno.take_profit import Noop as NoopTakeProfit
from juno.take_profit import TakeProfit
from juno.time import time_ms
from juno.trading import (
    CloseReason,
    Position,
    PositionMixin,
    SimulatedPositionMixin,
    StartMixin,
    TradingMode,
    TradingSummary,
)
from juno.typing import Constructor
from juno.utils import unpack_assets

from .trader import Trader

_log = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class BasicConfig:
    exchange: str
    symbol: str
    interval: Interval
    end: Timestamp
    strategy: Constructor[Signal]
    stop_loss: Optional[Constructor[StopLoss]] = None
    take_profit: Optional[Constructor[TakeProfit]] = None
    start: Optional[Timestamp] = None  # None means earliest is found.
    quote: Optional[Decimal] = None  # None means exchange wallet is queried.
    mode: TradingMode = TradingMode.BACKTEST
    channel: str = "default"
    missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE
    adjust_start: bool = True
    long: bool = True  # Take long positions.
    short: bool = False  # Take short positions.
    close_on_exit: bool = True  # Whether to close open position on exit.
    # Timeout in case no candle (including open) from exchange.
    exchange_candle_timeout: Optional[Interval] = None
    custodian: str = "stub"

    @property
    def base_asset(self) -> str:
        return unpack_assets(self.symbol)[0]

    @property
    def quote_asset(self) -> str:
        return unpack_assets(self.symbol)[1]


@dataclass
class BasicState:
    config: BasicConfig
    close_on_exit: bool

    strategy: Signal
    quote: Decimal
    summary: TradingSummary
    next_: Timestamp  # Candle time.
    real_start: Timestamp
    stop_loss: StopLoss
    take_profit: TakeProfit

    changed: Changed = field(default_factory=lambda: Changed(True))
    open_new_positions: bool = True  # Whether new positions can be opened.
    open_position: Optional[Position.Open] = None
    first_candle: Optional[Candle] = None
    last_candle: Optional[Candle] = None

    id: str = field(default_factory=lambda: str(uuid4()))
    running: bool = False

    @property
    def open_positions(self) -> list[Position.Open]:
        return [self.open_position] if self.open_position else []


class Basic(Trader[BasicConfig, BasicState], PositionMixin, SimulatedPositionMixin, StartMixin):
    @staticmethod
    def config() -> type[BasicConfig]:
        return BasicConfig

    @staticmethod
    def state() -> type[BasicState]:
        return BasicState

    def __init__(
        self,
        chandler: Chandler,
        informant: Informant,
        user: Optional[User] = None,
        broker: Optional[Broker] = None,  # Only required if not backtesting.
        custodians: list[Custodian] = [Stub()],
        events: Events = Events(),
        get_time_ms: Callable[[], int] = time_ms,
    ) -> None:
        self._chandler = chandler
        self._informant = informant
        self._user = user
        self._broker = broker
        self._custodians = {type(c).__name__.lower(): c for c in custodians}
        self._events = events
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
    def user(self) -> User:
        assert self._user
        return self._user

    @property
    def custodians(self) -> dict[str, Custodian]:
        return self._custodians

    async def open_positions(
        self, state: BasicState, symbols: list[str], short: bool
    ) -> list[Position.Open]:
        if len(symbols) == 0:
            return []

        queue = self._queues[state.id]

        if not state.running:
            raise ValueError("Trader not running")
        if queue.qsize() > 0:
            raise ValueError("Process with position already pending")
        if state.open_position:
            raise ValueError("Position already open")
        if len(symbols) > 1:
            raise ValueError("Can only open a single position")
        if symbols[0] != state.config.symbol:
            raise ValueError(f"Can only open {state.config.symbol} position")
        if not state.last_candle:
            raise ValueError("No candle received yet")

        coro: Union[Awaitable[Position.OpenLong], Awaitable[Position.OpenShort]] = (
            self._open_short_position(state, state.last_candle)
            if short
            else self._open_long_position(state, state.last_candle)
        )
        return [await process_task_on_queue(queue, coro)]

    async def close_positions(
        self, state: BasicState, symbols: list[str], reason: CloseReason
    ) -> list[Position.Closed]:
        if len(symbols) == 0:
            return []

        queue = self._queues[state.id]

        if not state.running:
            raise ValueError("Trader not running")
        if queue.qsize() > 0:
            raise ValueError("Process with position already pending")
        if not state.open_position:
            raise ValueError("No position open")
        if len(symbols) > 1:
            raise ValueError("Can only close a single position")
        if state.open_position.symbol != symbols[0]:
            raise ValueError(f"Only {state.open_position.symbol} position open")
        if not state.last_candle:
            raise ValueError("No candle received yet")

        return [await process_task_on_queue(queue, self._close_position(state, reason))]

    async def initialize(self, config: BasicConfig) -> BasicState:
        assert config.mode is TradingMode.BACKTEST or self.broker
        assert config.start is None or config.start >= 0
        assert config.end > 0
        assert config.start is None or config.end > config.start

        _, filters = self._informant.get_fees_filters(config.exchange, config.symbol)
        assert filters.spot
        if config.short:
            assert filters.isolated_margin

        start = await self.request_candle_start(
            config.start, config.exchange, [config.symbol], config.interval
        )
        real_start = self._get_time_ms()

        quote = await self._custodians[config.custodian].request_quote(
            exchange=config.exchange, asset=config.quote_asset, quote=config.quote
        )
        assert quote > filters.price.min

        strategy = config.strategy.construct()

        next_ = start
        if config.adjust_start:
            # Adjust start to accommodate for the required history before a strategy
            # becomes effective. Only do it on first run because subsequent runs mean
            # missed candles and we don't want to fetch passed a missed candle.
            _log.info(
                f"fetching {strategy.maturity - 1} candle(s) before start time to warm-up "
                "strategy"
            )
            next_ = max(next_ - (strategy.maturity - 1) * config.interval, 0)

        return BasicState(
            config=config,
            close_on_exit=config.close_on_exit,
            next_=next_,
            real_start=real_start,
            quote=quote,
            summary=TradingSummary(
                start=start if config.mode is TradingMode.BACKTEST else real_start,
                quote=quote,
                quote_asset=config.quote_asset,
            ),
            strategy=strategy,
            stop_loss=(
                NoopStopLoss() if config.stop_loss is None else config.stop_loss.construct()
            ),
            take_profit=(
                NoopTakeProfit() if config.take_profit is None else config.take_profit.construct()
            ),
        )

    async def run(self, state: BasicState) -> TradingSummary:
        config = state.config

        self._queues[state.id] = asyncio.Queue()
        state.running = True
        try:
            async for candle in self._chandler.stream_candles(
                exchange=config.exchange,
                symbol=config.symbol,
                interval=config.interval,
                start=state.next_,
                end=config.end,
                exchange_timeout=config.exchange_candle_timeout,
            ):
                # Check if we have missed a candle.
                if (last_candle := state.last_candle) and (
                    time_diff := (candle.time - last_candle.time)
                ) >= config.interval * 2:
                    if config.missed_candle_policy is MissedCandlePolicy.RESTART:
                        _log.info("restarting strategy due to missed candle(s)")
                        state.strategy = config.strategy.construct()
                    elif config.missed_candle_policy is MissedCandlePolicy.LAST:
                        num_missed = time_diff // config.interval - 1
                        _log.info(f"filling {num_missed} missed candles with last values")
                        for i in range(1, num_missed + 1):
                            missed_candle = Candle(
                                time=last_candle.time + i * config.interval,
                                open=last_candle.close,
                                high=last_candle.close,
                                low=last_candle.close,
                                close=last_candle.close,
                                volume=Decimal("0.0"),
                                closed=True,
                            )
                            await self._tick(state, missed_candle)

                await self._tick(state, candle)
        finally:
            state.running = False
            # Remove queue and wait for any pending position tasks to finish.
            queue = self._queues.pop(state.id)
            await queue.join()

            if state.close_on_exit and state.open_position:
                await self._close_position(state, CloseReason.CANCELLED)

            if config.end is not None and config.end <= state.real_start:  # Backtest.
                end = (
                    state.last_candle.time + config.interval
                    if state.last_candle
                    else state.summary.start + config.interval
                )
            else:  # Paper or live.
                end = min(self._get_time_ms(), config.end)
            state.summary.finish(end)

            if state.last_candle:
                _log.info(f"last candle: {state.last_candle}")

        _log.info("finished")
        return state.summary

    async def _tick(
        self,
        state: BasicState,
        candle: Candle,
    ) -> None:
        config = state.config

        assert state.strategy
        assert state.changed
        assert state.summary

        await self._events.emit(config.channel, "candle", candle)

        state.stop_loss.update(candle)
        state.take_profit.update(candle)
        state.strategy.update(candle)
        advice = state.changed.update(state.strategy.advice)
        _log.debug(f"received advice: {advice.name}")
        # Make sure strategy doesn't give advice during "adjusted start" period.
        if state.next_ < state.summary.start:
            assert advice is Advice.NONE

        queue = self._queues[state.id]
        coro: Optional[Awaitable]

        # Close existing position if requested.
        await queue.join()
        if state.open_position:
            coro = None

            if isinstance(state.open_position, Position.OpenLong):
                if advice in [Advice.SHORT, Advice.LIQUIDATE]:
                    coro = self._close_long_position(state, candle, CloseReason.STRATEGY)
                elif state.open_position and state.stop_loss.upside_hit:
                    assert advice is not Advice.LONG
                    _log.info(f"upside stop loss hit at {config.stop_loss}; selling")
                    coro = self._close_long_position(state, candle, CloseReason.STOP_LOSS)
                elif state.open_position and state.take_profit.upside_hit:
                    assert advice is not Advice.LONG
                    _log.info(f"upside take profit hit at {config.take_profit}; selling")
                    coro = self._close_long_position(state, candle, CloseReason.TAKE_PROFIT)
            elif isinstance(state.open_position, Position.OpenShort):
                if advice in [Advice.LONG, Advice.LIQUIDATE]:
                    coro = self._close_short_position(state, candle, CloseReason.STRATEGY)
                elif state.stop_loss.downside_hit:
                    assert advice is not Advice.SHORT
                    _log.info(f"downside stop loss hit at {config.stop_loss}; selling")
                    coro = self._close_short_position(state, candle, CloseReason.STOP_LOSS)
                elif state.take_profit.downside_hit:
                    assert advice is not Advice.SHORT
                    _log.info(f"downside take profit hit at {config.take_profit}; selling")
                    coro = self._close_short_position(state, candle, CloseReason.TAKE_PROFIT)

            if coro:
                await process_task_on_queue(queue, coro)

        # Open new position if requested.
        await queue.join()
        if not state.open_position and state.open_new_positions:
            coro = None

            if config.long and advice is Advice.LONG:
                coro = self._open_long_position(state, candle)
            elif config.short and advice is Advice.SHORT:
                coro = self._open_short_position(state, candle)

            if coro:
                await process_task_on_queue(queue, coro)

            state.stop_loss.clear(candle)
            state.take_profit.clear(candle)

        if not state.first_candle:
            _log.info(f"first candle: {candle}")
            state.first_candle = candle
        state.last_candle = candle
        state.next_ = candle.time + config.interval

    async def _close_position(
        self,
        state: BasicState,
        reason: CloseReason,
    ) -> Position.Closed:
        candle = state.last_candle
        open_position = state.open_position
        assert open_position
        assert candle
        if isinstance(open_position, Position.OpenLong):
            _log.info(f"{open_position.symbol} long position open; closing")
            return await self._close_long_position(state, candle, reason)
        elif isinstance(open_position, Position.OpenShort):
            _log.info(f"{open_position.symbol} short position open; closing")
            return await self._close_short_position(state, candle, reason)

    async def _open_long_position(self, state: BasicState, candle: Candle) -> Position.OpenLong:
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
            if config.mode is TradingMode.BACKTEST
            else await self.open_long_position(
                exchange=config.exchange,
                symbol=config.symbol,
                quote=state.quote,
                mode=config.mode,
                custodian=config.custodian,
            )
        )

        state.quote += position.quote_delta
        state.open_position = position

        await self._events.emit(
            config.channel, "positions_opened", [state.open_position], state.summary
        )
        return position

    async def _close_long_position(
        self, state: BasicState, candle: Candle, reason: CloseReason
    ) -> Position.Long:
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
            if config.mode is TradingMode.BACKTEST
            else await self.close_long_position(
                position=state.open_position,
                mode=config.mode,
                reason=reason,
                custodian=config.custodian,
            )
        )

        state.quote += position.quote_delta
        state.open_position = None
        state.summary.append_position(position)

        await self._events.emit(config.channel, "positions_closed", [position], state.summary)
        return position

    async def _open_short_position(self, state: BasicState, candle: Candle) -> Position.OpenShort:
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
            if config.mode is TradingMode.BACKTEST
            else await self.open_short_position(
                exchange=config.exchange,
                symbol=config.symbol,
                collateral=state.quote,
                mode=config.mode,
                custodian=config.custodian,
            )
        )

        state.quote += position.quote_delta
        state.open_position = position

        await self._events.emit(
            config.channel, "positions_opened", [state.open_position], state.summary
        )
        return position

    async def _close_short_position(
        self, state: BasicState, candle: Candle, reason: CloseReason
    ) -> Position.Short:
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
            if config.mode is TradingMode.BACKTEST
            else await self.close_short_position(
                position=state.open_position,
                mode=config.mode,
                reason=reason,
                custodian=config.custodian,
            )
        )

        state.quote += position.quote_delta
        state.open_position = None
        state.summary.append_position(position)

        await self._events.emit(config.channel, "positions_closed", [position], state.summary)
        return position
