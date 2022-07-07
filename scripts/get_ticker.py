import asyncio
import logging

from juno.exchanges import Exchange

EXCHANGE = "binance"
SYMBOL = "eth-btc"


async def main() -> None:
    exchange = Exchange.from_env(EXCHANGE)
    async with exchange:
        result = await exchange.map_tickers([SYMBOL])
        logging.info(f"Ticker {EXCHANGE} {SYMBOL}:\n{result[SYMBOL]}")


asyncio.run(main())
