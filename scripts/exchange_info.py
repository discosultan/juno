
import argparse
import asyncio
import logging

from juno import exchanges
from juno.config import from_env, init_instance
from juno.time import strfinterval
from juno.utils import get_module_type

parser = argparse.ArgumentParser()
parser.add_argument('exchange', nargs='?', default='binance')
parser.add_argument('symbol', nargs='?', default='eth-btc')
args = parser.parse_args()


async def main() -> None:
    async with init_instance(get_module_type(exchanges, args.exchange), from_env()) as client:
        exchange_info = await client.get_exchange_info()
        logging.info(exchange_info.fees.get('__all__') or exchange_info.fees[args.symbol])
        logging.info(list(map(strfinterval, client.list_candle_intervals())))
        logging.info(exchange_info.filters.get('__all__') or exchange_info.filters[args.symbol])


asyncio.run(main())
