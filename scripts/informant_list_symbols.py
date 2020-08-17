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
    default=None,
    help='if set, must support cross margin trading',
)
parser.add_argument(
    '-i', '--isolated',
    action='store_true',
    default=None,
    help='if set, must support isolated margin trading',
)
args = parser.parse_args()


async def main() -> None:
    storage = SQLite()
    exchange = init_instance(get_module_type(exchanges, args.exchange), from_env())
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
