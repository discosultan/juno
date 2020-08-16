import argparse
import asyncio
import logging

from juno import exchanges
from juno.asyncio import resolved_future
from juno.components import Wallet
from juno.config import from_env, init_instance
from juno.utils import get_module_type

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
            process_balances(wallet, 'spot'),
            (
                process_balances(wallet, 'margin')
                if client.can_margin_trade
                else resolved_future(None)
            ),
            # TODO: Add ISOLATED_MARGIN
        )


async def process_balances(wallet: Wallet, account: str) -> None:
    log_balances(wallet, account)
    if args.stream:
        while True:
            await wallet.get_updated_event(exchange=args.exchange, account=account).wait()
            log_balances(wallet, account)


def log_balances(wallet: Wallet, account: str) -> None:
    logging.info(f'{args.exchange} {account} account')
    balances = wallet.map_significant_balances(args.exchange, account=account)
    for asset, balance in balances.items():
        logging.info(f'{asset} - {balance}')
    if len(balances) == 0:
        logging.info('nothing to show')


asyncio.run(main())
