import importlib
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Generic, List, NamedTuple, Optional, TypeVar

from juno import Advice, Candle, Fill, InsufficientBalance, Interval, Timestamp, strategies
from juno.brokers import Broker
from juno.components import Chandler, Event, Informant
from juno.math import round_half_up
from juno.modules import get_module_type
from juno.strategies import Strategy
from juno.utils import tonamedtuple, unpack_symbol

from .common import MissedCandlePolicy, OpenPosition, TradingSummary

_log = logging.getLogger(__name__)

TStrategy = TypeVar('TStrategy', bound=Strategy)


class Trader:
    @dataclass
    class State(Generic[TStrategy]):
        strategy: Optional[TStrategy] = None
        quote: Decimal = Decimal('-1.0')
        summary: Optional[TradingSummary] = None
        open_position: Optional[OpenPosition] = None
        first_candle: Optional[Candle] = None
        last_candle: Optional[Candle] = None
        highest_close_since_position = Decimal('0.0')
        current: Timestamp = 0
        start_adjusted: bool = False

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

        @property
        def base_asset(self) -> str:
            return unpack_symbol(self.symbol)[0]

        @property
        def quote_asset(self) -> str:
            return unpack_symbol(self.symbol)[1]

        @property
        def trailing_factor(self) -> Decimal:
            return 1 - self.trailing_stop

        def new_strategy(self) -> Strategy:
            return get_module_type(importlib.import_module(self.strategy_module), self.strategy)(
                *self.strategy_args, **self.strategy_kwargs
            )

    def __init__(
        self,
        chandler: Chandler,
        informant: Informant,
        broker: Optional[Broker] = None,
        event: Event = Event(),
    ) -> None:
        self._chandler = chandler
        self._informant = informant
        self._broker = broker
        self._event = event

    async def run(self, config: Config, state: Optional[State] = None) -> TradingSummary:
        assert config.start >= 0
        assert config.end > 0
        assert config.end > config.start
        assert 0 <= config.trailing_stop < 1

        state = state or Trader.State()

        if state.quote == -1:
            state.quote = config.quote

        if not state.summary:
            state.summary = TradingSummary(start=config.start, quote=config.quote)

        if not state.strategy:
            state.strategy = config.new_strategy()

        if not state.current:
            state.current = config.start

        if config.adjust_start and not state.start_adjusted:
            # Adjust start to accommodate for the required history before a strategy
            # becomes effective. Only do it on first run because subsequent runs mean
            # missed candles and we don't want to fetch passed a missed candle.
            _log.info(
                f'fetching {state.strategy.maturity} candle(s) before start time to warm-up '
                'strategy'
            )
            state.current -= state.strategy.maturity * config.interval
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
                        state.last_candle
                        and candle.time - state.last_candle.time >= config.interval * 2
                    ):
                        # TODO: walrus operator
                        num_missed = (candle.time - state.last_candle.time) // config.interval - 1
                        if config.missed_candle_policy is MissedCandlePolicy.RESTART:
                            _log.info('restarting strategy due to missed candle(s)')
                            restart = True
                            state.strategy = config.new_strategy()
                            state.current = candle.time + config.interval
                        elif config.missed_candle_policy is MissedCandlePolicy.LAST:
                            _log.info(f'filling {num_missed} missed candles with last values')
                            last_candle = state.last_candle
                            for i in range(1, num_missed + 1):
                                missed_candle = Candle(
                                    time=last_candle.time + i * config.interval,
                                    open=last_candle.open,
                                    high=last_candle.high,
                                    low=last_candle.low,
                                    close=last_candle.close,
                                    volume=last_candle.volume,
                                    closed=last_candle.closed
                                )
                                await self._tick(config, state, missed_candle)

                    await self._tick(config, state, candle)

                    if restart:
                        break

                if not restart:
                    break
        finally:
            if state.last_candle and state.open_position:
                _log.info('ending trading but position open; closing')
                await self._close_position(config, state, state.last_candle)
            if state.last_candle:
                state.summary.finish(state.last_candle.time + config.interval)
            else:
                state.summary.finish(config.start)

        return state.summary

    async def _tick(self, config: Config, state: State, candle: Candle) -> None:
        await self._event.emit(config.channel, 'candle', candle)

        assert state.strategy
        advice = state.strategy.update(candle)

        if not state.open_position and advice is Advice.BUY:
            await self._open_position(config, state, candle)
            state.highest_close_since_position = candle.close
        elif state.open_position and advice is Advice.SELL:
            await self._close_position(config, state, candle)
        elif config.trailing_stop != 0 and state.open_position:
            state.highest_close_since_position = max(
                state.highest_close_since_position, candle.close
            )
            if candle.close <= state.highest_close_since_position * config.trailing_factor:
                _log.info(f'trailing stop hit at {config.trailing_stop}; selling')
                await self._close_position(config, state, candle)

        if not state.last_candle:
            _log.info(f'first candle {candle}')
            state.first_candle = candle
        state.last_candle = candle
        state.current = candle.time + config.interval

    async def _open_position(self, config: Config, state: State, candle: Candle) -> None:
        if self._broker:
            res = await self._broker.buy(
                exchange=config.exchange,
                symbol=config.symbol,
                quote=state.quote,
                test=config.test
            )

            state.open_position = OpenPosition(
                symbol=config.symbol,
                time=candle.time,
                fills=res.fills,
            )

            state.quote -= Fill.total_quote(res.fills)
        else:
            price = candle.close
            fees, filters = self._informant.get_fees_filters(config.exchange, config.symbol)

            size = filters.size.round_down(state.quote / price)
            if size == 0:
                raise InsufficientBalance()

            fee = round_half_up(size * fees.taker, filters.base_precision)

            state.open_position = OpenPosition(
                symbol=config.symbol,
                time=candle.time,
                fills=[Fill(price=price, size=size, fee=fee, fee_asset=config.base_asset)],
            )

            state.quote -= size * price

        _log.info(f'position opened: {candle}')
        _log.debug(tonamedtuple(state.open_position))
        await self._event.emit(
            config.channel, 'position_opened', state.open_position, state.summary
        )

    async def _close_position(self, config: Config, state: State, candle: Candle) -> None:
        assert state.summary
        assert state.open_position

        if self._broker:
            res = await self._broker.sell(
                exchange=config.exchange,
                symbol=config.symbol,
                base=state.open_position.base_gain,
                test=config.test
            )

            position = state.open_position.close(
                time=candle.time,
                fills=res.fills
            )

            state.quote += Fill.total_quote(res.fills) - Fill.total_fee(res.fills)
        else:
            price = candle.close
            fees, filters = self._informant.get_fees_filters(config.exchange, config.symbol)
            size = filters.size.round_down(state.open_position.base_gain)

            quote = size * price
            fee = round_half_up(quote * fees.taker, filters.quote_precision)

            position = state.open_position.close(
                time=candle.time,
                fills=[Fill(price=price, size=size, fee=fee, fee_asset=config.quote_asset)]
            )

            state.quote += quote - fee

        state.open_position = None
        state.summary.append_position(position)
        _log.info(f'position closed: {candle}')
        _log.debug(tonamedtuple(position))
        await self._event.emit(config.channel, 'position_closed', position, state.summary)
