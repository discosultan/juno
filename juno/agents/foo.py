import asyncio
import logging
from decimal import Decimal

from juno.components import Chandler, Historian, Informant, Prices
from juno.optimization import Optimizer, Solver
from juno.strategies import MAMACX
from juno.time import DAY_MS, strftimestamp, strpinterval, strptimestamp
from juno.trading import Trader, TradingSummary, get_benchmark_statistics, get_portfolio_statistics
from juno.utils import unpack_symbol

from .agent import Agent

_log = logging.getLogger(__name__)


class Foo(Agent):
    def __init__(
        self, chandler: Chandler, historian: Historian, informant: Informant, prices: Prices,
        solver: Solver
    ) -> None:
        super().__init__()
        self._chandler = chandler
        self._historian = historian
        self._informant = informant
        self._prices = prices
        self._solver = solver

    async def run(self) -> None:
        trading_start = strptimestamp('2019-07-01')
        end = strptimestamp('2020-01-01')
        exchange = 'binance'
        quote = Decimal('1.0')
        num_symbols = 2

        tickers = [t for t in self._informant.list_tickers(exchange) if t.symbol.endswith('-btc')]
        assert len(tickers) > num_symbols
        assert tickers[0].quote_volume > 0
        tickers.sort(key=lambda t: t.quote_volume, reverse=True)
        tickers = tickers[:num_symbols]
        symbols = [t.symbol for t in tickers]

        _log.info(f'found following top {num_symbols} symbols with highest 24h volume: {symbols}')

        quote_per_symbol = quote / len(symbols)

        summary = TradingSummary(quote=quote, start=trading_start)
        await asyncio.gather(
            *(self._optimize_and_trade(
                exchange,
                s,
                trading_start,
                end,
                quote_per_symbol,
                summary,
            ) for s in symbols)
        )
        summary.finish(end)

        # Statistics.
        daily_fiat_prices = await self._prices.map_daily_fiat_prices(
            {a for s in symbols for a in unpack_symbol(s)}, trading_start, end
        )

        benchmark_stats = get_benchmark_statistics(daily_fiat_prices['btc'])
        portfolio_stats = get_portfolio_statistics(benchmark_stats, daily_fiat_prices, summary)

        _log.info(f'benchmark stats: {benchmark_stats}')
        _log.info(f'portfolio stats: {portfolio_stats}')

    async def _optimize_and_trade(
        self,
        exchange: str,
        symbol: str,
        trading_start: int,
        end: int,
        quote: Decimal,
        summary: TradingSummary
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

        optimizer = Optimizer(
            solver=self._solver,
            chandler=self._chandler,
            informant=self._informant,
            prices=self._prices,
            exchange=exchange,
            start=optimization_start,
            end=trading_start,
            quote=quote,
            strategy_type=MAMACX,
            symbols=[symbol],
            intervals=list(map(strpinterval, ('30m', '1h', '2h'))),
            population_size=50,
            max_generations=100,
            seed=4842474260746992508
        )
        await optimizer.run()

        trader = Trader(
            chandler=self._chandler,
            informant=self._informant,
            exchange=exchange,
            symbol=symbol,
            interval=optimizer.result.interval,
            start=trading_start,
            end=end,
            quote=quote,
            new_strategy=lambda: MAMACX(**optimizer.result.strategy_config),
            missed_candle_policy=optimizer.result.missed_candle_policy,
            trailing_stop=optimizer.result.trailing_stop,
            summary=summary
        )
        await trader.run()
