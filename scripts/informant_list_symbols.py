import argparse
import asyncio
import logging

from juno import exchanges
from juno.components import Informant
from juno.config import from_env, init_instance
from juno.storages import SQLite
from juno.utils import get_module_type

parser = argparse.ArgumentParser()
parser.add_argument('exchange', nargs='?', default='binance')
parser.add_argument(
    '-m', '--margin',
    action='store_true',
    default=False,
    help='if set, must support margin trading',
)
args = parser.parse_args()


async def main() -> None:
    storage = SQLite()
    exchange = init_instance(get_module_type(exchanges, args.exchange), from_env())
    informant = Informant(storage, [exchange])
    async with exchange, informant:
        logging.info(type(exchange).__name__)
        logging.info(informant.list_symbols(args.exchange, short=args.margin))


asyncio.run(main())
