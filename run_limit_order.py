import asyncio
import logging
import os
import sys
from decimal import Decimal
from typing import List

from juno import Side
from juno.brokers import Limit, Market
from juno.components import Informant, Orderbook, Wallet
from juno.exchanges import Binance, Exchange
from juno.storages import Memory, SQLite

SIDE = Side.BID
EXCHANGE = 'binance'
SYMBOL = 'ada-btc'
LOG_LEVEL = 'DEBUG'
QUOTE = Decimal('0.0015')
BASE = Decimal('150')


if len(sys.argv) > 1:
    SIDE = Side[sys.argv[1].upper()]


async def main() -> None:
    binance = Binance(os.environ['JUNO__BINANCE__API_KEY'],
                      os.environ['JUNO__BINANCE__SECRET_KEY'])
    exchanges: List[Exchange] = [binance]
    memory = Memory()
    sqlite = SQLite()
    informant = Informant(storage=sqlite, exchanges=exchanges)
    orderbook = Orderbook(exchanges=exchanges, config={'symbol': SYMBOL})
    wallet = Wallet(exchanges=exchanges)
    market = Market(informant, orderbook, exchanges)
    limit = Limit(informant, orderbook, exchanges)
    async with binance, memory, sqlite, informant, orderbook, wallet:
        if SIDE is Side.BID:
            market_fills = market.find_order_asks(
                exchange=EXCHANGE,
                symbol=SYMBOL,
                quote=QUOTE)
            res = await limit.buy(
                exchange=EXCHANGE,
                symbol=SYMBOL,
                quote=QUOTE,
                test=False)
        else:
            market_fills = market.find_order_bids(
                exchange=EXCHANGE,
                symbol=SYMBOL,
                base=BASE)
            res = await limit.sell(
                exchange=EXCHANGE,
                symbol=SYMBOL,
                base=BASE,
                test=False)

        logging.info(res)
        logging.info(f'{SIDE} {SYMBOL}')
        logging.info(f'total size: {res.fills.total_size}')
        logging.info(f'total quote: {res.fills.total_quote}')
        logging.info(f'in case of market order total size: {market_fills.total_size}')
        logging.info(f'in case of market order total quote: {market_fills.total_quote}')

    logging.info('Done!')


logging.basicConfig(
    handlers=[logging.StreamHandler(stream=sys.stdout)],
    level=LOG_LEVEL)
asyncio.run(main())
