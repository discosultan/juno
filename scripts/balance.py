import argparse
import asyncio
import logging
from typing import Dict, List

from juno import Balance, exchanges
from juno.components import Wallet
from juno.config import from_env, init_instance
from juno.utils import get_module_type

parser = argparse.ArgumentParser()
parser.add_argument(
    'accounts', nargs='?', type=lambda a: a.split(','), default='spot,margin,isolated'
)
parser.add_argument('-e', '--exchange', default='binance')
parser.add_argument('--stream', action='store_true', default=False)
args = parser.parse_args()


async def main() -> None:
    client = init_instance(get_module_type(exchanges, args.exchange), from_env())
    wallet = Wallet([client])
    async with client, wallet:
        await log_accounts(wallet, args.accounts)
        if args.stream:
            if 'isolated' in args.accounts:
                raise ValueError('Cannot stream all isolated margin accounts')
            await asyncio.gather(*(stream_account(wallet, a) for a in args.accounts))


async def log_accounts(wallet: Wallet, accounts: List[str]) -> None:
    account_balances = await wallet.map_balances(
        exchange=args.exchange, accounts=accounts, significant=True
    )
    all_empty = True
    for account, account_balance in account_balances.items():
        if len(account_balance) > 0:
            all_empty = False
            logging.info(f'{args.exchange} {account} account')
            for asset, balance in account_balance.items():
                logging.info(f'{asset} - {balance}')
    if all_empty:
        logging.info('all accounts empty')


async def stream_account(wallet: Wallet, account: str) -> None:
    async with wallet.sync_balances(exchange=args.exchange, account=account) as ctx:
        while True:
            await ctx.updated.wait()
            log(account, ctx.balances)


def log(account: str, account_balances: Dict[str, Balance]) -> None:
    logging.info(f'{args.exchange} {account} account')
    for asset, balance in account_balances.items():
        logging.info(f'{asset} - {balance}')


asyncio.run(main())
