import asyncio
import logging
import os

from juno import exchanges

EXCHANGE_TYPE = exchanges.Binance
CLIENT_ID = 'foo'
SYMBOL = 'ada-btc'


async def main() -> None:
    name = EXCHANGE_TYPE.__name__.upper()
    async with EXCHANGE_TYPE(
        os.environ[f'JUNO__{name}__API_KEY'], os.environ[f'JUNO__{name}__SECRET_KEY']
    ) as client:
        res = await client.cancel_order(symbol=SYMBOL, client_id=CLIENT_ID)
        logging.info(res)
    logging.info('done')


asyncio.run(main())