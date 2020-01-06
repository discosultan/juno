import asyncio
import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from juno import Interval, Timestamp, strategies
from juno.asyncio import list_async
from juno.components import Chandler, Informant
from juno.config import init_module_instance
from juno.math import floor_multiple
from juno.time import DAY_MS, time_ms
from juno.trading import (
    MissedCandlePolicy, Trader, get_benchmark_statistics, get_portfolio_statistics
)

from .agent import Agent

_log = logging.getLogger(__name__)


class Backtest(Agent):
    def __init__(self, chandler: Chandler, informant: Informant) -> None:
        super().__init__()
        self.chandler = chandler
        self.informant = informant

    async def run(
        self,
        exchange: str,
        symbol: str,
        interval: Interval,
        start: Timestamp,
        quote: Decimal,
        strategy_config: Dict[str, Any],
        end: Optional[Timestamp] = None,
        missed_candle_policy: MissedCandlePolicy = MissedCandlePolicy.IGNORE,
        adjust_start: bool = True,
        trailing_stop: Decimal = Decimal('0.0'),
        analyze: bool = True,
    ) -> None:
        now = time_ms()

        start = floor_multiple(start, interval)
        if end is None:
            end = now
        end = floor_multiple(end, interval)

        assert end <= now
        assert end > start
        assert quote > 0

        trader = Trader(
            chandler=self.chandler,
            informant=self.informant,
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            quote=quote,
            new_strategy=lambda: init_module_instance(strategies, strategy_config),
            event=self,
            missed_candle_policy=missed_candle_policy,
            adjust_start=adjust_start,
            trailing_stop=trailing_stop,
        )
        self.result = trader.summary
        await trader.run()

        if not analyze:
            return

        start_day = floor_multiple(start, DAY_MS)
        end_day = floor_multiple(end, DAY_MS)

        # Find first exchange which supports the fiat pair.
        # btc_fiat_symbol = 'btc-eur'
        # btc_fiat_exchange = 'coinbase'
        # btc_fiat_exchanges = self.informant.list_exchanges_supporting_symbol(btc_fiat_symbol)
        # if len(btc_fiat_exchanges) == 0:
        #     _log.warning(f'no exchange with fiat symbol {btc_fiat_symbol} found; skipping '
        #                  'calculating further statistics')
        #     return
        # btc_fiat_exchange = btc_fiat_exchanges[0]

        # Fetch necessary market data.
        btc_fiat_daily, symbol_daily = await asyncio.gather(
            list_async(self.chandler.stream_candles(
                'coinbase', 'btc-eur', DAY_MS, start_day, end_day
            )),
            list_async(self.chandler.stream_candles(
                exchange, symbol, DAY_MS, start_day, end_day
            )),
        )

        benchmark_stats = get_benchmark_statistics(btc_fiat_daily)
        portfolio_stats = get_portfolio_statistics(
            benchmark_stats, btc_fiat_daily, symbol_daily, symbol, trader.summary
        )

        _log.info(f'benchmark stats: {benchmark_stats}')
        _log.info(f'portfolio stats: {portfolio_stats}')
