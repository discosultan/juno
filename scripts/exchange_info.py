import argparse
import asyncio
import logging

from juno import Interval_, serialization
from juno.exchanges import Exchange
from juno.path import save_json_file

parser = argparse.ArgumentParser()
parser.add_argument("exchange", nargs="?", default="binance")
parser.add_argument("symbol", nargs="?", default="eth-btc")
parser.add_argument(
    "--dump",
    action="store_true",
    default=False,
)
args = parser.parse_args()


async def main() -> None:
    async with Exchange.from_env(args.exchange) as exchange:
        exchange_info = await exchange.get_exchange_info()

        logging.info(exchange_info.fees.get(args.symbol) or exchange_info.fees["__all__"])
        logging.info(list(map(Interval_.format, exchange.list_candle_intervals())))
        logging.info(exchange_info.filters.get(args.symbol) or exchange_info.filters["__all__"])

        if args.dump:
            save_json_file(
                serialization.raw.serialize(exchange_info), "exchange_info.json", indent=4
            )


asyncio.run(main())
