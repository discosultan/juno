import argparse
import asyncio
import logging

from juno import Timestamp_
from juno.components import Chandler, Informant, Prices, Trades
from juno.exchanges import Exchange
from juno.storages import SQLite

parser = argparse.ArgumentParser()
parser.add_argument("assets", nargs="?", type=lambda s: s.split(","))
parser.add_argument("time", nargs="?", type=Timestamp_.parse)
parser.add_argument("-e", "--exchange", default="binance")
parser.add_argument("--target-asset", default="usdt")
args = parser.parse_args()


async def main() -> None:
    exchange = Exchange.from_env(args.exchange)
    sqlite = SQLite()
    informant = Informant(storage=sqlite, exchanges=[exchange])
    trades = Trades(storage=sqlite, exchanges=[exchange])
    chandler = Chandler(storage=sqlite, exchanges=[exchange], trades=trades)
    prices = Prices(informant=informant, chandler=chandler)
    async with exchange, informant, trades, chandler, prices:
        asset_prices = await prices.map_asset_prices_for_timestamp(
            exchange=args.exchange,
            assets=args.assets,
            time=args.time,
            target_asset=args.target_asset,
        )
        logging.info(f"{asset_prices}")


asyncio.run(main())
