import argparse
import asyncio
import logging
from decimal import Decimal

from juno import exchanges
from juno.components import Wallet
from juno.config import from_env, init_instance
from juno.utils import get_module_type

parser = argparse.ArgumentParser()
parser.add_argument('assets', nargs='?', type=lambda s: s.split(','), default='btc')
parser.add_argument('from_account', nargs='?', default='margin')
parser.add_argument('to_account', nargs='?', default='spot')
parser.add_argument('-e', '--exchange', default='binance')
parser.add_argument('-s', '--size', nargs='?', type=Decimal, default=None)
args = parser.parse_args()


async def main() -> None:
    client = init_instance(get_module_type(exchanges, args.exchange), from_env())
    wallet = Wallet([client])
    async with client, wallet:
        await asyncio.gather(*(transfer_asset(wallet, client, a) for a in args.assets))


async def transfer_asset(wallet: Wallet, client: exchanges.Exchange, asset: str) -> None:
    size = args.size
    if not size:
        balance = await wallet.get_balance(
            exchange=args.exchange, account=args.from_account, asset=asset
        )
        size = balance.available
    await client.transfer(
        asset=asset, size=size, from_account=args.from_account, to_account=args.to_account
    )
    logging.info(
        f'transferred {size} {asset} from {args.from_account} to {args.to_account} account'
    )


asyncio.run(main())
