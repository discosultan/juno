import asyncio
import logging
from decimal import Decimal
from typing import Any, List

from juno.components import Event, Historian, Informant, Prices
from juno.optimization import Optimizer
from juno.storages import Memory, Storage
from juno.time import DAY_MS, strftimestamp, strpinterval, strptimestamp
from juno.trading import Trader, analyse_benchmark, analyse_portfolio
from juno.utils import format_as_config, unpack_symbol

from .agent import Agent

_log = logging.getLogger(__name__)


class Foo(Agent):
    def __init__(
        self, historian: Historian, informant: Informant, prices: Prices, trader: Trader,
        optimizer: Optimizer, event: Event = Event(), storage: Storage = Memory()
    ) -> None:
        self._historian = historian
        self._informant = informant
        self._prices = prices
        self._trader = trader
        self._optimizer = optimizer
        self._event = event
        self._storage = storage

    async def on_running(self, config: Any, state: Agent.State[Trader.State]) -> None:
        await super().on_running(config, state)

        required_start = strptimestamp('2019-01-01')
        trading_start = strptimestamp('2019-07-01')
        end = strptimestamp('2020-01-01')
        exchange = 'binance'
        quote = Decimal('1.0')
        num_symbols = 4

        symbols = await self._find_top_symbols_by_volume_with_sufficient_history(
            exchange, required_start, num_symbols
        )
        quote_per_symbol = quote / len(symbols)

        state.result = Trader.State()
        await asyncio.gather(
            *(self._optimize_and_trade(
                exchange,
                s,
                trading_start,
                end,
                quote_per_symbol,
                state.result,
            ) for s in symbols)
        )
        assert state.result.summary
        state.result.summary.finish(end)

        # Statistics.
        fiat_daily_prices = await self._prices.map_fiat_daily_prices(
            exchange, {a for s in symbols for a in unpack_symbol(s)}, trading_start, end
        )

        benchmark = analyse_benchmark(fiat_daily_prices['btc'])
        portfolio = analyse_portfolio(benchmark.g_returns, fiat_daily_prices, state.result.summary)

        _log.info(f'benchmark stats: {format_as_config(benchmark.stats)}')
        _log.info(f'portfolio stats: {format_as_config(portfolio.stats)}')

    async def _find_top_symbols_by_volume_with_sufficient_history(
        self, exchange: str, required_start: int, count: int
    ) -> List[str]:
        tickers = [t for t in self._informant.list_tickers(exchange) if t.symbol.endswith('-btc')]

        assert any(t.quote_volume > 0 for t in tickers)
        tickers.sort(key=lambda t: t.quote_volume, reverse=True)

        symbols = []
        skipped_symbols = []
        for ticker in tickers:
            first_candle = await self._historian.find_first_candle(exchange, ticker.symbol, DAY_MS)
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
        exchange: str,
        symbol: str,
        trading_start: int,
        end: int,
        quote: Decimal,
        state: Trader.State
    ) -> None:
        optimization_start = (
            await self._historian.find_first_candle(exchange, symbol, DAY_MS)
        ).time

        if optimization_start > trading_start:
            raise ValueError(
                f'Requested {exchange} {symbol} trading start {strftimestamp(trading_start)} but '
                f'first candle found at {strftimestamp(optimization_start)}'
            )
        else:
            _log.info(
                f'first {exchange} {symbol} candle found from {strftimestamp(optimization_start)}'
            )

        optimization_summary = await self._optimizer.run(
            exchange=exchange,
            start=optimization_start,
            end=trading_start,
            quote=quote,
            strategy='mamacx',
            symbols=[symbol],
            intervals=list(map(strpinterval, ('2h',))),
            population_size=10,
            max_generations=100,
        )
        tc = optimization_summary.best[0].trading_config._asdict()
        tc.update({
            'start': trading_start,
            'end': end,
        })

        await self._trader.run(Trader.Config(**tc), state)
