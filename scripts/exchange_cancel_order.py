import asyncio
import logging

from juno import exchanges
from juno.config import config_from_env, load_instance

EXCHANGE_TYPE = exchanges.Binance
CLIENT_ID = 'foo'
SYMBOL = 'ada-btc'


async def main() -> None:
    async with load_instance(EXCHANGE_TYPE, config_from_env()) as client:
        res = await client.cancel_order(symbol=SYMBOL, client_id=CLIENT_ID)
        logging.info(res)
    logging.info('done')


asyncio.run(main())
