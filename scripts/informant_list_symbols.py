import argparse
import asyncio
import logging

from juno.components import Informant
from juno.exchanges import Exchange
from juno.storages import SQLite

parser = argparse.ArgumentParser()
parser.add_argument("exchange", nargs="?", default="binance")
parser.add_argument(
    "-m",
    "--margin",
    action="store_true",
    default=None,
    help="if set, must support cross margin trading",
)
parser.add_argument(
    "-i",
    "--isolated",
    action="store_true",
    default=None,
    help="if set, must support isolated margin trading",
)
args = parser.parse_args()


async def main() -> None:
    storage = SQLite()
    exchange = Exchange.from_env(args.exchange)
    informant = Informant(storage, [exchange])
    async with exchange, informant:
        logging.info(type(exchange).__name__)
        logging.info(
            informant.list_symbols(
                args.exchange,
                spot=True,
                cross_margin=args.margin,
                isolated_margin=args.isolated_margin,
            )
        )


asyncio.run(main())
