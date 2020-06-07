import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import List, NamedTuple, Optional

from juno import Interval, Timestamp
from juno.brokers import Broker
from juno.components import Chandler, Informant, Wallet
from juno.optimizer import Optimizer
from juno.strategies import Strategy
from juno.time import DAY_MS, strftimestamp, strpinterval, strptimestamp
from juno.trading import TradingSummary
from juno.typing import TypeConstructor
from juno.utils import construct

from .basic import Basic
from .trader import Trader

_log = logging.getLogger(__name__)


class Optimizing(Trader):
    class Config(NamedTuple):
        exchange: str
        interval: Interval
        end: Timestamp
        quote: Decimal
        strategy: TypeConstructor[Strategy]
        start: Optional[Timestamp] = None
        channel: str = 'default'
        long: bool = True
        short: bool = False
        fiat_exchange: Optional[str] = None
        fiat_asset: str = 'usdt'

    @dataclass
    class State:
        summary: Optional[TradingSummary] = None

    def __init__(
        self, chandler: Chandler, informant: Informant, basic: Basic, optimizer: Optimizer
    ) -> None:
        self._chandler = chandler
        self._informant = informant
        self._basic = basic
        self._optimizer = optimizer

    @property
    def broker(self) -> Broker:
        return self._basic.broker

    @property
    def chandler(self) -> Chandler:
        return self._chandler

    @property
    def wallet(self) -> Wallet:
        return self._basic.wallet

    async def run(self, config: Config, state: Optional[State] = None) -> TradingSummary:
        required_start = strptimestamp('2019-01-01')
        trading_start = strptimestamp('2019-07-01')
        end = strptimestamp('2020-01-01')
        exchange = 'binance'
        quote = Decimal('1.0')
        num_symbols = 4

        symbols = await self._find_top_symbols_by_volume_with_sufficient_history(
            exchange, required_start, num_symbols, config.short
        )
        quote_per_symbol = quote / len(symbols)

        state = state or Optimizing.State()

        if not state.summary:
            state.summary = TradingSummary(
                start=trading_start,
                quote=quote,
                quote_asset='btc',
            )

        await asyncio.gather(
            *(self._optimize_and_trade(
                config,
                s,
                trading_start,
                end,
                quote_per_symbol,
                state.summary,
            ) for s in symbols)
        )
        state.summary.finish(end)
        return state.summary

    async def _find_top_symbols_by_volume_with_sufficient_history(
        self, exchange: str, required_start: int, count: int, short: bool
    ) -> List[str]:
        tickers = self._informant.list_tickers(exchange, symbol_pattern='*-btc', short=short)
        assert any(t.quote_volume > 0 for t in tickers)

        symbols = []
        skipped_symbols = []
        for ticker in tickers:
            first_candle = await self._chandler.get_first_candle(exchange, ticker.symbol, DAY_MS)
            if first_candle.time > required_start:
                skipped_symbols.append(ticker.symbol)
                continue

            symbols.append(ticker.symbol)
            if len(symbols) == count:
                break

        assert len(symbols) > 0

        msg = f'found following top {count} symbols with highest 24h volume: {symbols}'
        if len(skipped_symbols) > 0:
            msg += (
                f'; skipped the following {len(skipped_symbols)} symbols because they were '
                f'launched after {strftimestamp(required_start)}: {", ".join(skipped_symbols)}'
            )
        _log.info(msg)

        return symbols

    async def _optimize_and_trade(
        self,
        config: Config,
        symbol: str,
        trading_start: int,
        end: int,
        quote: Decimal,
        summary: TradingSummary,
    ) -> None:
        optimization_start = (
            await self._chandler.get_first_candle(config.exchange, symbol, DAY_MS)
        ).time

        if optimization_start > trading_start:
            raise ValueError(
                f'Requested {config.exchange} {symbol} trading start '
                f'{strftimestamp(trading_start)} but first candle found at '
                f'{strftimestamp(optimization_start)}'
            )
        else:
            _log.info(
                f'first {config.exchange} {symbol} candle found from '
                f'{strftimestamp(optimization_start)}'
            )

        optimization_summary = await self._optimizer.run(
            Optimizer.Config(
                exchange=config.exchange,
                start=optimization_start,
                end=trading_start,
                quote=quote,
                strategy='mamacx',
                symbols=[symbol],
                intervals=list(map(strpinterval, ('2h',))),
                population_size=10,
                max_generations=100,
                long=config.long,
                short=config.short,
                fiat_asset=config.fiat_asset,
                fiat_exchange=config.fiat_exchange,
            )
        )

        trader_config = construct(
            Basic.Config,
            optimization_summary.trading_config,
            start=trading_start,
            end=end,
            channel=config.channel,
        )
        trader_state = Basic.State(summary=summary)
        await self._basic.run(trader_config, trader_state)
