import asyncio
import logging

import juno.json as json
from juno import exchanges, time
from juno.components import Chandler
from juno.config import from_env, init_instance
from juno.storages import SQLite
from juno.trading import get_benchmark_statistics

EXCHANGE_TYPE = exchanges.Coinbase
SYMBOL = 'btc-eur'
INTERVAL = time.DAY_MS
START = time.strptimestamp('2019-01-01')
END = time.strptimestamp('2020-01-01')

DUMP_AS_JSON = True


async def main() -> None:
    sqlite = SQLite()
    client = init_instance(EXCHANGE_TYPE, from_env())
    exchange_name = EXCHANGE_TYPE.__name__.lower()
    chandler = Chandler(storage=sqlite, exchanges=[client])
    async with client:
        candles = await chandler.list_candles(
            exchange_name, SYMBOL, INTERVAL, START, END, fill_missing_with_last=True
        )
        statistics = get_benchmark_statistics(candles)

    if DUMP_AS_JSON:
        with open(f'{exchange_name}_{SYMBOL}_{INTERVAL}_statistics.json', 'w') as f:
            json.dump(statistics, f, indent=4)

    logging.info('done')


asyncio.run(main())
