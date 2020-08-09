import argparse
import asyncio
import logging

from juno import AccountType, exchanges
from juno.config import from_env, init_instance
from juno.utils import get_module_type

parser = argparse.ArgumentParser()
parser.add_argument(
    'account',
    nargs='?',
    type=lambda s: AccountType[s.upper()],
    default=AccountType.SPOT,
)
# parser.add_argument('isolated_symbol', nargs='?', default=None)
parser.add_argument(
    '-e',
    '--exchange',
    type=lambda e: get_module_type(exchanges, e),
    default=exchanges.Binance,
)
args = parser.parse_args()


async def main() -> None:
    async with init_instance(args.exchange, from_env()) as client:
        balances = await client.map_balances(margin=args.account is AccountType.CROSS_MARGIN)
        logging.info(balances)


asyncio.run(main())
