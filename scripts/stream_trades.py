import asyncio
import logging

from asyncstdlib import enumerate as enumerate_async

from juno import Timestamp_, storages
from juno.components import Trades
from juno.exchanges import Exchange

EXCHANGE = "kraken"
SYMBOL = "eth-btc"


async def main() -> None:
    storage = storages.SQLite()
    exchange = Exchange.from_env(EXCHANGE)
    trades = Trades(storage, [exchange])
    async with exchange, trades:
        start = Timestamp_.parse("2019-03-22T08:00")
        end = Timestamp_.parse("2019-04-02T16:00")
        logging.info(f"start {start}; end {end}")

        async for i, trade in enumerate_async(trades.stream_trades(EXCHANGE, SYMBOL, start, end)):
            logging.info(f"trade[{i}]: {trade}")
            if i == 2:
                break


asyncio.run(main())
