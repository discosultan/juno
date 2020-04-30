import argparse
import asyncio
import logging

from juno import exchanges
from juno.config import from_env, init_instance

EXCHANGE_TYPE = exchanges.Binance
CLIENT_ID = 'b311e925-6c5c-40ad-b73d-e79494af4d81'
SYMBOL = 'eth-btc'

parser = argparse.ArgumentParser()
parser.add_argument('symbol', nargs='?', default=SYMBOL)
parser.add_argument('client_id', nargs='?', default=CLIENT_ID)
args = parser.parse_args()


async def main() -> None:
    async with init_instance(EXCHANGE_TYPE, from_env()) as client:
        res = await client.cancel_order(symbol=args.symbol, client_id=args.client_id)
        logging.info(res)


asyncio.run(main())
