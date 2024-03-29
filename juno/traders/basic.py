import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Awaitable, Callable, Literal, Optional, TypeVar, Union
from uuid import uuid4

from juno import (
    Advice,
    BadOrder,
    Candle,
    CandleType,
    Interval,
    Symbol,
    Symbol_,
    Timestamp,
    Timestamp_,
)
from juno.asyncio import process_task_on_queue
from juno.brokers import Broker
from juno.common import CandleMeta
from juno.components import Chandler, Events, Informant, Orderbook, User
from juno.custodians import Custodian, Stub
from juno.exchanges import Exchange
from juno.inspect import Constructor
from juno.positioner import Positioner, SimulatedPositioner
from juno.stop_loss import Noop as NoopStopLoss
from juno.stop_loss import StopLoss
from juno.strategies import Changed, Signal
from juno.take_profit import Noop as NoopTakeProfit
from juno.take_profit import TakeProfit
from juno.trading import CloseReason, Position, StartMixin, TradingMode, TradingSummary

from .trader import Trader

_log = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class BasicConfig:
    exchange: str
    symbol: Symbol
    interval: Interval
    end: Timestamp
    strategy: Constructor[Signal]
    stop_loss: Optional[Constructor[StopLoss]] = None
    take_profit: Optional[Constructor[TakeProfit]] = None
    start: Optional[Timestamp] = None  # None means earliest is found.
    quote: Optional[Decimal] = None  # None means exchange wallet is queried.
    mode: TradingMode = TradingMode.BACKTEST
    channel: str = "default"
    adjusted_start: Optional[Union[Timestamp, Literal["strategy"]]] = None
    long: bool = True  # Take long positions.
    short: bool = True  # Take short positions.
    close_on_exit: bool = True  # Whether to close open position on exit.
    custodian: str = "stub"
    candle_type: CandleType = "regular"

    @property
    def base_asset(self) -> str:
        return Symbol_.assets(self.symbol)[0]

    @property
    def quote_asset(self) -> str:
        return Symbol_.assets(self.symbol)[1]


@dataclass
class BasicState:
    config: BasicConfig
    close_on_exit: bool

    strategy: Signal
    starting_quote: Decimal
    quote: Decimal
    next_: Timestamp  # Candle time.
    start: Timestamp
    real_start: Timestamp
    stop_loss: StopLoss
    take_profit: TakeProfit

    changed: Changed = field(default_factory=lambda: Changed(True))
    open_new_positions: bool = True  # Whether new positions can be opened.
    positions: list[Position.Closed] = field(default_factory=list)
    open_position: Optional[Position.Open] = None
    first_candle: Optional[Candle] = None
    last_candle: Optional[Candle] = None

    id: str = field(default_factory=lambda: str(uuid4()))
    running: bool = False

    @property
    def open_positions(self) -> list[Position.Open]:
        return [self.open_position] if self.open_position else []


class Basic(Trader[BasicConfig, BasicState], StartMixin):
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
        get_time_ms: Callable[[], int] = Timestamp_.now,
        exchanges: Optional[list[Exchange]] = None,
        orderbook: Optional[Orderbook] = None,
    ) -> None:
        self._chandler = chandler
        self._informant = informant
        self._broker = broker
        if (
            user is not None
            and broker is not None
            and exchanges is not None
            and orderbook is not None
        ):
            self._positioner = Positioner(
                informant=informant,
                chandler=chandler,
                orderbook=orderbook,
                broker=broker,
                user=user,
                custodians=custodians,
                exchanges=exchanges,
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

        return [
            await process_task_on_queue(
                queue, self._open_position(state, short, state.last_candle)
            )
        ]

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

        return [
            await process_task_on_queue(
                queue, self._close_position(state, reason, state.last_candle)
            )
        ]

    async def initialize(self, config: BasicConfig) -> BasicState:
        assert config.mode is TradingMode.BACKTEST or self._positioner
        assert config.start is None or config.start >= 0
        assert config.end > 0
        assert config.start is None or config.end > config.start

        _, filters = self._informant.get_fees_filters(config.exchange, config.symbol)
        assert filters.spot
        if config.short:
            assert filters.cross_margin or filters.isolated_margin

        start = await self.request_candle_start(
            config.start, config.exchange, [config.symbol], config.interval
        )
        real_start = self._get_time_ms()

        quote = await self._custodians[config.custodian].request(
            exchange=config.exchange, asset=config.quote_asset, amount=config.quote
        )
        assert quote > filters.price.min

        strategy = config.strategy.construct()

        next_ = Trader.adjust_start(
            start=start,
            adjusted_start=config.adjusted_start,
            strategy_maturity=strategy.maturity,
            candle_type=config.candle_type,
            interval=config.interval,
        )

        return BasicState(
            config=config,
            close_on_exit=config.close_on_exit,
            start=start,
            real_start=real_start,
            next_=next_,
            quote=quote,
            starting_quote=quote,
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
            _log.info(
                f"streaming candles between {Timestamp_.format_span(state.next_, config.end)}"
            )
            async for candle, candle_meta in self._chandler.stream_concurrent_candles(
                exchange=config.exchange,
                entries=(
                    [(config.symbol, config.interval, config.candle_type)]
                    + state.strategy.extra_candles
                ),
                start=state.next_,
                end=config.end,
            ):
                await self._tick(state, candle, candle_meta)
            _log.info("ran out of candles; finishing")
        except BadOrder:
            _log.exception("bad order; finishing early")
        finally:
            state.running = False
            # Remove queue and wait for any pending position tasks to finish.
            queue = self._queues.pop(state.id)
            await queue.join()

            if state.close_on_exit and state.open_position:
                assert state.last_candle
                await self._close_position(state, CloseReason.CANCELLED, state.last_candle)

            if state.last_candle:
                _log.info(f"last {config.candle_type} candle: {state.last_candle}")

        _log.info("finished")
        return self.build_summary(state)

    async def _tick(
        self,
        state: BasicState,
        candle: Candle,
        candle_meta: CandleMeta,
    ) -> None:
        config = state.config
        is_main_candle = candle_meta == (config.symbol, config.interval, config.candle_type)

        await self._events.emit(config.channel, "candle", candle)

        if is_main_candle:
            state.stop_loss.update(candle)
            state.take_profit.update(candle)

        state.strategy.update(candle, candle_meta)
        advice = Advice.NONE
        if is_main_candle:
            # Make sure strategy doesn't give advice during "adjusted start" period.
            advice = (
                state.changed.update(state.strategy.advice)
                if state.next_ >= state.start
                else Advice.NONE
            )
            _log.debug(f"received advice: {advice.name}")
            if advice is not Advice.NONE:
                assert state.strategy.mature

        queue = self._queues[state.id]
        coro: Optional[Awaitable]

        # Close existing position if requested.
        await queue.join()
        if state.open_position:
            coro = None

            if isinstance(state.open_position, Position.OpenLong):
                if advice in {Advice.SHORT, Advice.LIQUIDATE}:
                    coro = self._close_position(state, CloseReason.STRATEGY, candle)
                elif state.open_position and state.stop_loss.upside_hit:
                    assert advice is not Advice.LONG
                    _log.info(f"upside stop loss hit at {config.stop_loss}; selling")
                    coro = self._close_position(state, CloseReason.STOP_LOSS, candle)
                elif state.open_position and state.take_profit.upside_hit:
                    assert advice is not Advice.LONG
                    _log.info(f"upside take profit hit at {config.take_profit}; selling")
                    coro = self._close_position(state, CloseReason.TAKE_PROFIT, candle)
            elif isinstance(state.open_position, Position.OpenShort):
                if advice in {Advice.LONG, Advice.LIQUIDATE}:
                    coro = self._close_position(state, CloseReason.STRATEGY, candle)
                elif state.stop_loss.downside_hit:
                    assert advice is not Advice.SHORT
                    _log.info(f"downside stop loss hit at {config.stop_loss}; selling")
                    coro = self._close_position(state, CloseReason.STOP_LOSS, candle)
                elif state.take_profit.downside_hit:
                    assert advice is not Advice.SHORT
                    _log.info(f"downside take profit hit at {config.take_profit}; selling")
                    coro = self._close_position(state, CloseReason.TAKE_PROFIT, candle)

            if coro:
                await process_task_on_queue(queue, coro)

        # Open new position if requested.
        await queue.join()
        if not state.open_position and state.open_new_positions:
            coro = None

            if config.long and advice is Advice.LONG:
                coro = self._open_position(state, False, candle)
            elif config.short and advice is Advice.SHORT:
                coro = self._open_position(state, True, candle)

            if coro:
                await process_task_on_queue(queue, coro)

            state.stop_loss.clear(candle)
            state.take_profit.clear(candle)

        if not state.first_candle:
            _log.info(f"first {config.candle_type} candle: {candle}")
            state.first_candle = candle
        state.last_candle = candle
        state.next_ = candle.time + config.interval

    async def _open_position(
        self,
        state: BasicState,
        short: bool,
        candle: Candle,
    ) -> Position.Open:
        config = state.config
        assert not state.open_position

        (position,) = (
            self._simulated_positioner.open_simulated_positions(
                exchange=config.exchange,
                entries=[
                    (
                        config.symbol,
                        state.quote,
                        short,
                        candle.time + config.interval,
                        candle.close,
                    )
                ],
            )
            if config.mode is TradingMode.BACKTEST
            else await self._positioner.open_positions(
                exchange=config.exchange,
                custodian=config.custodian,
                mode=config.mode,
                entries=[(config.symbol, state.quote, short)],
            )
        )

        state.quote -= position.cost
        state.open_position = position

        await self._events.emit(
            config.channel, "positions_opened", [state.open_position], self.build_summary(state)
        )
        return position

    async def _close_position(
        self,
        state: BasicState,
        reason: CloseReason,
        candle: Candle,
    ) -> Position.Closed:
        config = state.config
        open_position = state.open_position

        assert open_position

        (position,) = (
            self._simulated_positioner.close_simulated_positions(
                entries=[(open_position, reason, candle.time + config.interval, candle.close)],
            )
            if config.mode is TradingMode.BACKTEST
            else await self._positioner.close_positions(
                custodian=config.custodian,
                mode=config.mode,
                entries=[(open_position, reason)],
            )
        )

        state.quote += position.gain
        state.open_position = None
        state.positions.append(position)

        await self._events.emit(
            config.channel, "positions_closed", [position], self.build_summary(state)
        )
        return position

    def build_summary(self, state: BasicState) -> TradingSummary:
        config = state.config
        start = state.start if config.mode is TradingMode.BACKTEST else state.real_start
        if config.end is not None and config.end <= state.real_start:  # Backtest.
            end = (
                state.last_candle.time + config.interval
                if state.last_candle
                else start + config.interval
            )
        else:  # Paper or live.
            end = min(self._get_time_ms(), config.end)

        return TradingSummary(
            start=start,
            end=end,
            starting_assets={
                state.config.quote_asset: state.starting_quote,
            },
            positions=list(state.positions),
        )
