import argparse
import asyncio
import logging
from decimal import Decimal

import juno.json as json
from juno import exchanges, strategies
from juno.components import Chandler, Informant
from juno.config import format_as_config, from_env, init_instance
from juno.statistics import CoreStatistics
from juno.storages import SQLite
from juno.time import DAY_MS, strptimestamp
from juno.traders import Basic, BasicConfig
from juno.trading import TradingSummary
from juno.typing import type_to_raw
from juno.utils import get_module_type

parser = argparse.ArgumentParser()
parser.add_argument('-e', '--exchange', default='binance')
parser.add_argument('--dump', action='store_true', default=False)
args = parser.parse_args()


async def main() -> None:
    client = init_instance(get_module_type(exchanges, args.exchange), from_env())
    storage = SQLite()

    chandler = Chandler(storage, [client])
    informant = Informant(storage, [client])
    trader = Basic(chandler, informant)
    async with client, storage, chandler, informant:
        summary = await backtest(trader)
    stats = CoreStatistics.compose(summary)
    logging.info(format_as_config(stats))

    if args.dump:
        with open('trading_summary.json', 'w') as file:
            json.dump(type_to_raw(summary), file, indent=4)


async def backtest(trader: Basic) -> TradingSummary:
    state = await trader.initialize(BasicConfig(
        exchange=args.exchange,
        symbol='eth-btc',
        interval=DAY_MS,
        start=strptimestamp('2018-01-01'),
        end=strptimestamp('2021-01-01'),
        strategy=strategies.FourWeekRuleParams(  # type: ignore
            period=28,
            ma='ema',
            ma_period=14,
        ),
        quote=Decimal('1.0'),
        long=True,
        short=True,
    ))
    return await trader.run(state)


asyncio.run(main())
