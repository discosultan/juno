import argparse
import asyncio
import logging

from juno import exchanges
from juno.config import from_env, init_instance

EXCHANGE_TYPE = exchanges.Binance
CLIENT_ID = 'b311e925-6c5c-40ad-b73d-e79494af4d81'

parser = argparse.ArgumentParser()
parser.add_argument('symbol', nargs='?', default='eth-btc')
parser.add_argument('client_id', nargs='?', default=CLIENT_ID)
parser.add_argument(
    '-m', '--margin',
    action='store_true',
    default=False,
    help='if set, use margin; otherwise spot account',
)
args = parser.parse_args()


async def main() -> None:
    async with init_instance(EXCHANGE_TYPE, from_env()) as client:
        res = await client.cancel_order(
            symbol=args.symbol, client_id=args.client_id, margin=args.margin
        )
        logging.info(res)


asyncio.run(main())
