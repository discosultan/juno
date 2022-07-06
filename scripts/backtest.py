import argparse
import asyncio
import logging
from decimal import Decimal
from typing import Any

from juno import Interval_, Timestamp_, json, serialization, stop_loss, strategies, take_profit
from juno.asyncio import gather_dict
from juno.components import Chandler, Informant
from juno.exchanges import Exchange
from juno.inspect import GenericConstructor
from juno.path import save_json_file
from juno.statistics import CoreStatistics
from juno.storages import SQLite
from juno.traders import Basic, BasicConfig
from juno.trading import TradingSummary

parser = argparse.ArgumentParser()
parser.add_argument("-e", "--exchange", default="binance")
parser.add_argument("--dump", action="store_true", default=False)
args = parser.parse_args()

STRATEGIES = [
    strategies.FourWeekRuleParams(
        period=28,
        ma="ema",
        ma_period=14,
    ),
    strategies.SingleMAParams(
        ma="ema",
        period=50,
    ),
    strategies.DoubleMAParams(
        short_ma="ema",
        long_ma="ema",
        short_period=5,
        long_period=20,
    ),
    strategies.TripleMAParams(
        short_ma="ema",
        medium_ma="ema",
        long_ma="ema",
        short_period=4,
        medium_period=9,
        long_period=18,
    ),
]


async def main() -> None:
    exchange = Exchange.from_env(args.exchange)
    storage = SQLite()

    chandler = Chandler(storage, [exchange])
    informant = Informant(storage, [exchange])
    trader = Basic(chandler, informant)
    async with exchange, storage, chandler, informant:
        summaries_stats = await gather_dict(
            {type(strategy).__name__: backtest(trader, strategy) for strategy in STRATEGIES}
        )

    if args.dump:
        stats = {k: v[1] for k, v in summaries_stats.items()}
        dump("strategies.json", serialization.raw.serialize(stats))


async def backtest(trader: Basic, strategy: Any) -> tuple[TradingSummary, CoreStatistics]:
    state = await trader.initialize(
        BasicConfig(
            exchange=args.exchange,
            symbol="eth-btc",
            interval=Interval_.DAY,
            start=Timestamp_.parse("2018-01-01"),
            end=Timestamp_.parse("2021-01-01"),
            strategy=strategy,
            # stop_loss=TypeConstructor.from_type(stop_loss.Noop),
            # take_profit=TypeConstructor.from_type(take_profit.Noop),
            stop_loss=GenericConstructor.from_type(
                stop_loss.Basic,
                Decimal("0.1"),
            ),
            take_profit=GenericConstructor.from_type(
                take_profit.Basic,
                Decimal("0.1"),
            ),
            quote=Decimal("1.0"),
            long=True,
            short=True,
            adjusted_start=None,
            custodian="stub",
        )
    )
    summary = await trader.run(state)
    stats = CoreStatistics.compose(summary)
    logging.info(json.dumps(serialization.config.serialize(stats), indent=4))
    return summary, stats


def dump(name: str, data: Any) -> None:
    if name.endswith(".json"):
        save_json_file(data, name, indent=4)
    else:
        raise NotImplementedError()


asyncio.run(main())
