import argparse
import asyncio
import logging

from juno import exchanges
from juno.components import Wallet
from juno.config import from_env, init_instance
from juno.utils import get_module_type

parser = argparse.ArgumentParser()
parser.add_argument(
    'accounts', nargs='?', type=lambda a: a.split(','), default='spot,margin,isolated'
)
parser.add_argument('-e', '--exchange', default='binance')
args = parser.parse_args()


async def main() -> None:
    client = init_instance(get_module_type(exchanges, args.exchange), from_env())
    wallet = Wallet([client])
    async with client, wallet:
        await log_balances(wallet)


async def log_balances(wallet: Wallet) -> None:
    account_balances = await wallet.map_balances(
        exchange=args.exchange, accounts=args.accounts, significant=True
    )
    for account, account_balance in account_balances.items():
        logging.info(f'{args.exchange} {account} account')
        if len(account_balance) == 0:
            logging.info('nothing to show')
        else:
            for asset, balance in account_balance.items():
                logging.info(f'{asset} - {balance}')


asyncio.run(main())
