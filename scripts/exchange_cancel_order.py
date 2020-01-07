import asyncio
import logging

from juno import exchanges
from juno.config import from_env, init_instance

EXCHANGE_TYPE = exchanges.Binance
CLIENT_ID = 'foo'
SYMBOL = 'ada-btc'


async def main() -> None:
    async with init_instance(EXCHANGE_TYPE, from_env()) as client:
        res = await client.cancel_order(symbol=SYMBOL, client_id=CLIENT_ID)
        logging.info(res)
    logging.info('done')


asyncio.run(main())
