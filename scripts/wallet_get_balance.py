import asyncio
import logging

from juno import exchanges
from juno.components import Wallet
from juno.config import from_env, init_instance

EXCHANGE_TYPE = exchanges.Binance
ASSETS = ['btc', 'eth']


async def main() -> None:
    client = init_instance(EXCHANGE_TYPE, from_env())
    name = EXCHANGE_TYPE.__name__.lower()
    wallet = Wallet([client])
    async with client, wallet:
        for asset in ASSETS:
            print(f'{asset} - {wallet.get_balance(name, asset)}')
    logging.info('done')


asyncio.run(main())
