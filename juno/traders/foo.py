import asyncio
import logging
from decimal import Decimal
from typing import Any, List, Optional

from juno.components import Chandler, Events, Informant, Prices
from juno.optimization import Optimizer
from juno.statistics import analyse_benchmark, analyse_portfolio
from juno.time import DAY_MS, strftimestamp, strpinterval, strptimestamp
from juno.trading import TradingSummary
from juno.utils import format_as_config

from .basic import Basic
from .trader import Trader

_log = logging.getLogger(__name__)


class Foo(Trader):
    def __init__(
        self, chandler: Chandler, informant: Informant, prices: Prices, trader: Basic,
        optimizer: Optimizer, events: Events = Events()
    ) -> None:
        self._chandler = chandler
        self._informant = informant
        self._prices = prices
        self._trader = trader
        self._optimizer = optimizer
        self._events = events

    async def run(self, config: Any, state: Optional[State]) -> TradingSummary:
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

        state.result = self._trader.State()
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

    async def _find_top_symbols_by_volume_with_sufficient_history(
        self, exchange: str, required_start: int, count: int
    ) -> List[str]:
        tickers = self._informant.list_tickers(exchange, symbol_pattern='*-btc')
        assert any(t.quote_volume > 0 for t in tickers)

        symbols = []
        skipped_symbols = []
        for ticker in tickers:
            first_candle = await self._chandler.find_first_candle(exchange, ticker.symbol, DAY_MS)
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
        state: Any,
    ) -> None:
        optimization_start = (
            await self._chandler.find_first_candle(exchange, symbol, DAY_MS)
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

        await self._trader.run(self._trader.Config(**tc), state)
