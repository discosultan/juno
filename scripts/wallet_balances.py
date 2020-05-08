import argparse
import asyncio
import logging

from juno import exchanges
from juno.asyncio import resolved_future
from juno.components import Wallet
from juno.config import from_env, init_instance
from juno.modules import get_module_type

KEEP_STREAMING = False

parser = argparse.ArgumentParser()
parser.add_argument('exchange', nargs='?', default='binance')
parser.add_argument(
    '-s', '--stream', default=False, action='store_true', help='keep streaming balance updates'
)
args = parser.parse_args()


async def main() -> None:
    client = init_instance(get_module_type(exchanges, args.exchange), from_env())
    wallet = Wallet([client])
    async with client, wallet:
        await asyncio.gather(
            process_balances(wallet, False),
            process_balances(wallet, True) if client.can_margin_trade else resolved_future(None),
        )


async def process_balances(wallet: Wallet, margin: bool) -> None:
    log_balances(wallet, margin)
    if KEEP_STREAMING:
        while True:
            await wallet.get_updated_event(exchange=args.exchange, margin=margin).wait()
            log_balances(wallet, margin)


def log_balances(wallet: Wallet, margin: bool) -> None:
    logging.info(f'{args.exchange.upper()} {"MARGIN" if margin else "SPOT"} ACCOUNT')
    balances = wallet.map_significant_balances(args.exchange, margin=margin)
    for asset, balance in balances.items():
        logging.info(f'{asset} - {balance}')
    if len(balances) == 0:
        logging.info('nothing to show')


asyncio.run(main())
