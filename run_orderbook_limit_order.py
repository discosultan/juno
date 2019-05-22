import asyncio
import logging
import os
import sys
from decimal import Decimal

from juno import Side
from juno.components import Informant, Orderbook, Wallet
from juno.exchanges import Binance
from juno.storages import Memory, SQLite

SIDE = Side.BUY
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
    memory = Memory()
    sqlite = SQLite()
    async with binance, memory, sqlite:
        informant = Informant(storage=sqlite, exchanges=[binance])
        orderbook = Orderbook(informant=informant, exchanges=[binance], config={'symbol': SYMBOL})
        wallet = Wallet(exchanges=[binance])
        async with informant, orderbook, wallet:
            if SIDE is Side.BUY:
                market_fills = orderbook.find_market_order_asks(
                    exchange=EXCHANGE,
                    symbol=SYMBOL,
                    quote=QUOTE)
                res = await orderbook.buy_limit_at_spread(
                    exchange=EXCHANGE,
                    symbol=SYMBOL,
                    quote=QUOTE,
                    test=False)
            else:
                market_fills = orderbook.find_market_order_bids(
                    exchange=EXCHANGE,
                    symbol=SYMBOL,
                    base=BASE)
                res = await orderbook.sell_limit_at_spread(
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
