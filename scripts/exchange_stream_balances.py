import argparse
import asyncio
import logging

from juno import exchanges
from juno.config import from_env, init_instance
from juno.utils import get_module_type

parser = argparse.ArgumentParser()
parser.add_argument('account', nargs='?', default='spot')
parser.add_argument('-e', '--exchange', default='binance')
args = parser.parse_args()


async def main() -> None:
    logging.info(f'streaming balances from {args.exchange} {args.account} account')
    client = init_instance(get_module_type(exchanges, args.exchange), from_env())
    async with client:
        async with client.connect_stream_balances(account=args.account) as stream:
            async for val in stream:
                logging.info(val)


asyncio.run(main())
