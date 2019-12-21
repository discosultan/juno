import asyncio
import logging
import os

from juno import exchanges
from juno.components import Wallet

EXCHANGE_TYPE = exchanges.Binance
ASSETS = ['btc', 'eth']


async def main():
    name = EXCHANGE_TYPE.__name__.upper()
    client = EXCHANGE_TYPE(
        os.environ[f'JUNO__{name}__API_KEY'], os.environ[f'JUNO__{name}__SECRET_KEY']
    )
    name = name.lower()
    wallet = Wallet([client])
    async with client, wallet:
        for asset in ASSETS:
            print(f'{asset} - {wallet.get_balance(name, asset)}')
    logging.info('done')


asyncio.run(main())
