import argparse
import asyncio
import logging

from juno.exchanges import Exchange

parser = argparse.ArgumentParser()
parser.add_argument('account', nargs='?', default='spot')
parser.add_argument('-e', '--exchange', default='binance')
args = parser.parse_args()


async def main() -> None:
    logging.info(f'streaming balances from {args.exchange} {args.account} account')
    exchange = Exchange.from_env(args.exchange)
    async with exchange:
        async with exchange.connect_stream_balances(account=args.account) as stream:
            async for val in stream:
                logging.info(val)


asyncio.run(main())
