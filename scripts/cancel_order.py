import argparse
import asyncio
import logging

from juno.exchanges import Exchange

CLIENT_ID = 'b311e925-6c5c-40ad-b73d-e79494af4d81'

parser = argparse.ArgumentParser()
parser.add_argument('account', nargs='?', default='spot')
parser.add_argument('symbol', nargs='?', default='eth-btc')
parser.add_argument('client_id', nargs='?', default=CLIENT_ID)
parser.add_argument('-e', '--exchange', default='binance')
args = parser.parse_args()


async def main() -> None:
    async with Exchange.from_env(args.exchange) as exchange:
        res = await exchange.cancel_order(
            account=args.account, symbol=args.symbol, client_id=args.client_id
        )
        logging.info(res)


asyncio.run(main())
