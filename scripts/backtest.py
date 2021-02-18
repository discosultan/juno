import argparse
import asyncio
import logging
from decimal import Decimal
from typing import Any

import juno.json as json
from juno import MissedCandlePolicy, exchanges, stop_loss, strategies, take_profit
from juno.asyncio import gather_dict
from juno.components import Chandler, Informant
from juno.config import format_as_config, from_env, init_instance, type_to_config
from juno.statistics import CoreStatistics
from juno.storages import SQLite
from juno.time import DAY_MS, strptimestamp
from juno.traders import Basic, BasicConfig
from juno.trading import TradingSummary
from juno.typing import TypeConstructor, type_to_raw
from juno.utils import get_module_type

parser = argparse.ArgumentParser()
parser.add_argument('-e', '--exchange', default='binance')
parser.add_argument('--dump', action='store_true', default=False)
args = parser.parse_args()

STRATEGIES = [
    strategies.FourWeekRuleParams(
        period=28,
        ma='ema',
        ma_period=14,
    ),
    strategies.SingleMAParams(
        ma='ema',
        period=50,
    ),
    strategies.DoubleMAParams(
        short_ma='ema',
        long_ma='ema',
        short_period=5,
        long_period=20,
    ),
    strategies.TripleMAParams(
        short_ma='ema',
        medium_ma='ema',
        long_ma='ema',
        short_period=4,
        medium_period=9,
        long_period=18,
    ),
]


async def main() -> None:
    client = init_instance(get_module_type(exchanges, args.exchange), from_env())
    storage = SQLite()

    chandler = Chandler(storage, [client])
    informant = Informant(storage, [client])
    trader = Basic(chandler, informant)
    async with client, storage, chandler, informant:
        stats = await gather_dict(
            {type(strategy).__name__: backtest(trader, strategy) for strategy in STRATEGIES}
        )

    if args.dump:
        with open('tests/data/strategies.json', 'w') as file:
            json.dump(type_to_raw(stats), file, indent=4)


async def backtest(trader: Basic, strategy: Any) -> CoreStatistics:
    state = await trader.initialize(BasicConfig(
        exchange=args.exchange,
        symbol='eth-btc',
        interval=DAY_MS,
        start=strptimestamp('2018-01-01'),
        end=strptimestamp('2021-01-01'),
        strategy=strategy,
        # stop_loss=TypeConstructor.from_type(stop_loss.Noop),
        # take_profit=TypeConstructor.from_type(take_profit.Noop),
        stop_loss=TypeConstructor.from_type(
            stop_loss.Basic,
            Decimal('0.1'),
        ),
        take_profit=TypeConstructor.from_type(
            take_profit.Basic,
            Decimal('0.1'),
        ),
        quote=Decimal('1.0'),
        long=True,
        short=True,
        missed_candle_policy=MissedCandlePolicy.IGNORE,
        adjust_start=False,
    ))
    summary = await trader.run(state)
    # dump_summary(summary)
    stats = CoreStatistics.compose(summary)
    logging.info(format_as_config(stats))
    return stats


def dump_summary(summary: TradingSummary) -> None:
    with open('py_dump.json', 'w') as file:
        json.dump(type_to_config(summary, TradingSummary), file, indent=4)


asyncio.run(main())
