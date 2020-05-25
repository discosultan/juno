import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, NamedTuple, Optional

from juno import Advice, Candle, Fill, Interval, MissedCandlePolicy, Timestamp
from juno.brokers import Broker
from juno.components import Chandler, Events, Informant, Wallet
from juno.exchanges import Exchange
from juno.strategies import Changed, Strategy
from juno.time import strftimestamp
from juno.trading import Position, PositionMixin, SimulatedPositionMixin, TradingSummary
from juno.typing import TypeConstructor
from juno.utils import extract_public, unpack_symbol

from .trader import Trader

_log = logging.getLogger(__name__)


class Basic(Trader, PositionMixin, SimulatedPositionMixin):
    class Config(NamedTuple):
        exchange: str
        symbol: str
        interval: Interval
        end: Timestamp
        strategy: TypeConstructor[Strategy]
        start: Optional[Timestamp] = None  # None means earliest is found.
        quote: Optional[Decimal] = None  # None means exchange wallet is queried.
        trailing_stop: Decimal = Decimal('0.0')  # 0 means disabled.
        test: bool = True  # No effect if broker is None.
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

    @dataclass
    class State:
        strategy: Optional[Strategy] = None
        changed: Changed = field(default_factory=lambda: Changed(True))
        quote: Decimal = Decimal('-1.0')
        summary: Optional[TradingSummary] = None
        open_position: Optional[Position.Open] = None
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
        wallet: Optional[Wallet] = None,
        broker: Optional[Broker] = None,
        events: Events = Events(),
        exchanges: List[Exchange] = [],
    ) -> None:
        self._chandler = chandler
        self._informant = informant
        self._wallet = wallet
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
        assert config.start is None or config.start >= 0
        assert config.end > 0
        assert config.start is None or config.end > config.start
        assert 0 <= config.trailing_stop < 1
        if config.short:
            assert self._informant.get_borrow_info(config.exchange, config.quote_asset)
            assert self._informant.get_fees_filters(
                config.exchange, config.symbol
            )[1].is_margin_trading_allowed

        # Resolve and assert available quote.
        if (quote := config.quote) is None:
            assert self._wallet
            quote = self._wallet.get_balance(
                config.exchange, config.quote_asset
            ).available
            _log.info(f'quote not specified; using available {quote} {config.quote_asset}')
        fees, filters = self._informant.get_fees_filters(config.exchange, config.symbol)
        assert quote > filters.price.min

        # Resolve start.
        if (start := config.start) is None:
            start = (await self._chandler.find_first_candle(
                config.exchange, config.symbol, config.interval
            )).time
            _log.info(f'start not specified; start set to {strftimestamp(start)}')

        state = state or Basic.State()

        if state.quote == -1:
            state.quote = quote

        if not state.summary:
            state.summary = TradingSummary(
                start=start,
                quote=quote,
                quote_asset=config.quote_asset,
            )

        if not state.strategy:
            state.strategy = config.strategy.construct()

        if not state.current:
            state.current = start

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
                            state.strategy = config.strategy.construct()
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
                if isinstance(state.open_position, Position.OpenLong):
                    _log.info('ending trading but long position open; closing')
                    await self._close_long_position(config, state, state.last_candle)
                elif isinstance(state.open_position, Position.OpenShort):
                    _log.info('ending trading but short position open; closing')
                    await self._close_short_position(config, state, state.last_candle)

                state.summary.finish(state.last_candle.time + config.interval)
            else:
                state.summary.finish(start)

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

        if isinstance(state.open_position, Position.OpenLong):
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
        elif isinstance(state.open_position, Position.OpenShort):
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

        if not state.open_position:
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
        assert not state.open_position

        position = (
            await self.open_long_position(
                exchange=config.exchange,
                symbol=config.symbol,
                time=candle.time,
                quote=state.quote,
                test=config.test,
            ) if self._broker else self.open_simulated_long_position(
                exchange=config.exchange,
                symbol=config.symbol,
                time=candle.time,
                price=candle.close,
                quote=state.quote,
            )
        )

        state.quote -= Fill.total_quote(position.fills)
        state.open_position = position

        _log.info(f'long position opened: {candle}')
        _log.debug(extract_public(state.open_position))
        await self._events.emit(
            config.channel, 'position_opened', state.open_position, state.summary
        )

    async def _close_long_position(self, config: Config, state: State, candle: Candle) -> None:
        assert state.summary
        assert isinstance(state.open_position, Position.OpenLong)

        position = (
            await self.close_long_position(
                position=state.open_position,
                time=candle.time,
                test=config.test,
            ) if self._broker else self.close_simulated_long_position(
                position=state.open_position,
                time=candle.time,
                price=candle.close,
            )
        )

        state.quote += (
            Fill.total_quote(position.close_fills) - Fill.total_fee(position.close_fills)
        )
        state.open_position = None
        state.summary.append_position(position)

        _log.info(f'long position closed: {candle}')
        _log.debug(extract_public(position))
        await self._events.emit(config.channel, 'position_closed', position, state.summary)

    async def _open_short_position(self, config: Config, state: State, candle: Candle) -> None:
        assert not state.open_position

        position = (
            await self.open_short_position(
                exchange=config.exchange,
                symbol=config.symbol,
                time=candle.time,
                price=candle.close,
                collateral=state.quote,
                test=config.test,
            ) if self._broker else self.open_simulated_short_position(
                exchange=config.exchange,
                symbol=config.symbol,
                time=candle.time,
                price=candle.close,
                collateral=state.quote,
            )
        )

        state.quote += Fill.total_quote(position.fills) - Fill.total_fee(position.fills)
        state.open_position = position

        _log.info(f'short position opened: {candle}')
        _log.debug(extract_public(state.open_position))
        await self._events.emit(
            config.channel, 'position_opened', state.open_position, state.summary
        )

    async def _close_short_position(self, config: Config, state: State, candle: Candle) -> None:
        assert state.summary
        assert isinstance(state.open_position, Position.OpenShort)

        position = (
            await self.close_short_position(
                position=state.open_position,
                time=candle.time,
                price=candle.close,
                test=config.test,
            ) if self._broker else self.close_simulated_short_position(
                position=state.open_position,
                time=candle.time,
                price=candle.close,
            )
        )

        state.quote -= Fill.total_quote(position.close_fills)
        state.open_position = None
        state.summary.append_position(position)

        _log.info(f'short position closed: {candle}')
        _log.debug(extract_public(position))
        await self._events.emit(config.channel, 'position_closed', position, state.summary)
