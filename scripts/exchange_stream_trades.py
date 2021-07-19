import asyncio
import logging

from juno.exchanges import Exchange

EXCHANGE = "kraken"
SYMBOL = "btc-eur"


async def main() -> None:
    async with Exchange.from_env(EXCHANGE) as exchange:
        async with exchange.connect_stream_trades(symbol=SYMBOL) as stream:
            i = 0
            async for val in stream:
                logging.info(val)
                i += 1
                if i == 2:
                    break


asyncio.run(main())
