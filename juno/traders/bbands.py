import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Awaitable, Callable, Optional, TypeVar
from uuid import uuid4

from juno import Advice, BadOrder, Candle, Timestamp
from juno.asyncio import process_task_on_queue
from juno.brokers import Broker
from juno.components import Chandler, Events, Informant, User
from juno.custodians import Stub
from juno.indicators import Bbands, Obv
from juno.positioner import Positioner, SimulatedPositioner
from juno.stop_loss import Noop as NoopStopLoss
from juno.stop_loss import StopLoss
from juno.strategies.strategy import Changed
from juno.take_profit import Noop as NoopTakeProfit
from juno.take_profit import TakeProfit
from juno.time import HOUR_MS, MIN_MS, floor_timestamp, time_ms
from juno.trading import CloseReason, Position, StartMixin, TradingMode, TradingSummary
from juno.typing import Constructor
from juno.utils import unpack_assets

from .trader import Trader

_log = logging.getLogger(__name__)

T = TypeVar("T")

# 3m
# 24h -> 480 candles
# 2h  -> 40 candles
# 1h  -> 20 candles
# 30m -> 10 candles
# 15m -> 5 candles
_num_3m_candles = 20

# 5m
# 24h -> 288 candles
# 2h  -> 24 candles
# 1h  -> 12 candles
# 30m -> 6 candles
# 15m -> 3 candles
_num_5m_candles = 12


class BBandsStrategy:
    def __init__(self) -> None:
        self._bb = Bbands(20, Decimal("2.0"))
        self._3m_candles: list[Candle] = []
        self._5m_candles: list[Candle] = []
        self._previous_trend = 0  # 1 up; 0 none; -1 down
        self._trend = 0
        self._previous_outside_bb = 0  # 1 outside upper; 0 inside; -1 outside lower
        self._outside_bb = 0
        self._advice = Advice.NONE
        self._changed = Changed(enabled=True)

    @property
    def mature(self) -> bool:
        return (
            self._bb.mature
            and len(self._3m_candles) == _num_3m_candles
            and len(self._5m_candles) == _num_5m_candles
        )

    def update(self, candle: Candle, candle_meta: tuple[str, int]) -> Advice:
        _, interval = candle_meta

        if interval == MIN_MS:
            # Update current outside bb.
            self._bb.update(candle.close)
            self._outside_bb = (
                1 if candle.close > self._bb.upper else -1 if candle.close < self._bb.lower else 0
            )
        elif interval == 3 * MIN_MS:
            if len(self._3m_candles) == _num_3m_candles:
                self._3m_candles.pop(0)
            self._3m_candles.append(candle)
        elif interval == 5 * MIN_MS:
            if len(self._5m_candles) == _num_5m_candles:
                self._5m_candles.pop(0)
            self._5m_candles.append(candle)
        else:
            raise ValueError("Unexpected candle interval")

        if self.mature and interval == MIN_MS:
            # Update current trend.
            obv3 = Obv()
            for candle3 in self._3m_candles:
                obv3.update(candle3.close, candle3.volume)
            obv5 = Obv()
            for candle5 in self._5m_candles:
                obv5.update(candle5.close, candle5.volume)

            self._trend = (
                1
                if obv3.value > 0 and obv5.value > 0
                else -1
                if obv3.value < 0 and obv5.value < 0
                else 0
            )

            # Update advice.

            # Open position if previous outside bb and current back in.
            # if self._previous_outside_bb == -1 and self._outside_bb == 0:
            #     self._advice = Advice.LONG
            # elif self._previous_outside_bb == 1 and self._outside_bb == 0:
            #     self._advice = Advice.SHORT

            # Open position if previous outside bb and current back in and is matching trend.
            if self._previous_outside_bb == -1 and self._outside_bb == 0 and self._trend == 1:
                self._advice = Advice.LONG
            elif self._previous_outside_bb == 1 and self._outside_bb == 0 and self._trend == -1:
                self._advice = Advice.SHORT

            # Close position if trend turns opposite.
            # elif self._advice is Advice.LONG and self._trend == -1:
            #     self._advice = Advice.LIQUIDATE
            # elif self._advice is Advice.SHORT and self._trend == 1:
            #     self._advice = Advice.LIQUIDATE

            # Close position if trend turns opposite or neutral.
            elif self._advice is Advice.LONG and self._trend != 1:
                self._advice = Advice.LIQUIDATE
            elif self._advice is Advice.SHORT and self._trend != -1:
                self._advice = Advice.LIQUIDATE

            # Close position if outside bb on the opposite side from opening.
            elif self._advice is Advice.LONG and self._outside_bb == 1:
                self._advice = Advice.LIQUIDATE
            elif self._advice is Advice.SHORT and self._outside_bb == -1:
                self._advice = Advice.LIQUIDATE

        if interval == MIN_MS:
            # Update previous outside bb and trend.
            self._previous_outside_bb = self._outside_bb
            self._previous_trend = self._trend

        return self._changed.update(self._advice)


@dataclass(frozen=True)
class BBandsConfig:
    exchange: str
    symbol: str
    end: Timestamp
    start: Optional[Timestamp] = None  # None means earliest is found.
    quote: Optional[Decimal] = None  # None means exchange wallet is queried.
    mode: TradingMode = TradingMode.BACKTEST
    channel: str = "default"
    close_on_exit: bool = True  # Whether to close open position on exit.
    stop_loss: Optional[Constructor[StopLoss]] = None
    take_profit: Optional[Constructor[TakeProfit]] = None

    @property
    def base_asset(self) -> str:
        return unpack_assets(self.symbol)[0]

    @property
    def quote_asset(self) -> str:
        return unpack_assets(self.symbol)[1]


@dataclass
class BBandsState:
    config: BBandsConfig
    close_on_exit: bool

    strategy: BBandsStrategy
    starting_quote: Decimal
    quote: Decimal
    next_: Timestamp  # Candle time.
    candle_start: Timestamp  # Candle time.
    start: Timestamp
    real_start: Timestamp
    stop_loss: StopLoss
    take_profit: TakeProfit

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


# 3m 5m check 24h trend with obv
# 1m trading with bbands 20 2
class BBandsTrader(Trader[BBandsConfig, BBandsState], StartMixin):
    @staticmethod
    def config() -> type[BBandsConfig]:
        return BBandsConfig

    @staticmethod
    def state() -> type[BBandsState]:
        return BBandsState

    def __init__(
        self,
        chandler: Chandler,
        informant: Informant,
        user: Optional[User] = None,
        broker: Optional[Broker] = None,  # Only required if not backtesting.
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
                custodians=[Stub()],
            )
        self._simulated_positioner = SimulatedPositioner(informant=informant)
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
        self, state: BBandsState, symbols: list[str], short: bool
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
        self, state: BBandsState, symbols: list[str], reason: CloseReason
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

    async def initialize(self, config: BBandsConfig) -> BBandsState:
        assert config.mode is TradingMode.BACKTEST or self._positioner
        assert config.start is None or config.start >= 0
        assert config.end > 0
        assert config.start is None or config.end > config.start

        _, filters = self._informant.get_fees_filters(config.exchange, config.symbol)
        assert filters.spot

        start = await self.request_candle_start(
            config.start, config.exchange, [config.symbol], MIN_MS
        )
        real_start = self._get_time_ms()

        quote = config.quote
        assert quote
        assert quote > filters.price.min

        next_ = start
        _log.info("fetching candles 24 hours before start time to warm-up strategy")
        next_ = max(next_ - 24 * HOUR_MS, 0)

        return BBandsState(
            config=config,
            close_on_exit=config.close_on_exit,
            next_=next_,
            candle_start=start,
            real_start=real_start,
            start=start if config.mode is TradingMode.BACKTEST else real_start,
            strategy=BBandsStrategy(),
            quote=quote,
            starting_quote=quote,
            stop_loss=(
                NoopStopLoss() if config.stop_loss is None else config.stop_loss.construct()
            ),
            take_profit=(
                NoopTakeProfit() if config.take_profit is None else config.take_profit.construct()
            ),
        )

    async def run(self, state: BBandsState) -> TradingSummary:
        config = state.config

        self._queues[state.id] = asyncio.Queue()
        state.running = True
        try:
            async for candle_meta, candle in self._chandler.stream_concurrent_candles(
                exchange=config.exchange,
                entries=[
                    (config.symbol, MIN_MS),
                    (config.symbol, 3 * MIN_MS),
                    (config.symbol, 5 * MIN_MS),
                ],
                start=state.next_,
                end=config.end,
            ):
                await self._tick(state, candle_meta, candle)
        except BadOrder:
            _log.info("ran out of funds; finishing early")
        finally:
            state.running = False
            # Remove queue and wait for any pending position tasks to finish.
            queue = self._queues.pop(state.id)
            await queue.join()

            if state.close_on_exit and state.open_position:
                assert state.last_candle
                await self._close_position(state, CloseReason.CANCELLED, state.last_candle)

            if state.last_candle:
                _log.info(f"last candle: {state.last_candle}")

        _log.info("finished")
        return self.build_summary(state)

    async def _tick(
        self,
        state: BBandsState,
        candle_meta: tuple[str, int],
        candle: Candle,
    ) -> None:
        config = state.config

        await self._events.emit(config.channel, "candle", candle)

        advice = state.strategy.update(candle, candle_meta)
        if candle_meta[1] == MIN_MS:
            state.stop_loss.update(candle)
            state.take_profit.update(candle)

        if candle.time < floor_timestamp(state.candle_start, candle_meta[1]):
            advice = Advice.NONE
        _log.debug(f"received advice: {advice.name}")

        # Make sure strategy doesn't give advice during "adjusted start" period.
        if state.next_ < state.start:
            assert advice is Advice.NONE

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

            if advice is Advice.LONG:
                coro = self._open_position(state, False, candle)
            elif advice is Advice.SHORT:
                coro = self._open_position(state, True, candle)

            if coro:
                await process_task_on_queue(queue, coro)

            state.stop_loss.clear(candle)
            state.take_profit.clear(candle)

        if not state.first_candle:
            _log.info(f"first candle: {candle}")
            state.first_candle = candle
        state.last_candle = candle
        state.next_ = candle.time + MIN_MS

    async def _open_position(
        self,
        state: BBandsState,
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
                        candle.time + MIN_MS,
                        candle.close,
                    )
                ],
            )
            if config.mode is TradingMode.BACKTEST
            else await self._positioner.open_positions(
                exchange=config.exchange,
                custodian="stub",
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
        state: BBandsState,
        reason: CloseReason,
        candle: Candle,
    ) -> Position.Closed:
        config = state.config
        open_position = state.open_position

        assert open_position

        (position,) = (
            self._simulated_positioner.close_simulated_positions(
                entries=[(open_position, reason, candle.time + MIN_MS, candle.close)],
            )
            if config.mode is TradingMode.BACKTEST
            else await self._positioner.close_positions(
                custodian="stub",
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

    def build_summary(self, state: BBandsState) -> TradingSummary:
        config = state.config
        if config.end is not None and config.end <= state.real_start:  # Backtest.
            end = (
                state.last_candle.time + MIN_MS
                if state.last_candle
                else state.candle_start + MIN_MS
            )
        else:  # Paper or live.
            end = min(self._get_time_ms(), config.end)

        return TradingSummary(
            start=state.candle_start,
            end=end,
            starting_assets={
                state.config.quote_asset: state.starting_quote,
            },
            positions=list(state.positions),
        )
