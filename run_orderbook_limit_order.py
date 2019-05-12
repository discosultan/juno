import asyncio
import logging
import os
import sys
from decimal import Decimal

from juno import Side
from juno.components import Informant, Orderbook, Wallet
from juno.exchanges import Binance
from juno.storages import Memory, SQLite

SIDE = Side.SELL
EXCHANGE = 'binance'
SYMBOL = 'ada-btc'
LOG_LEVEL = 'DEBUG'
QUOTE = Decimal('0.0015')
BASE = Decimal('150')


async def main() -> None:
    binance = Binance(os.environ['JUNO__BINANCE__API_KEY'],
                      os.environ['JUNO__BINANCE__SECRET_KEY'])
    memory = Memory()
    sqlite = SQLite()
    async with binance, memory, sqlite:
        services = {'binance': binance, 'memory': memory, 'sqlite': sqlite}
        config = {'symbol': SYMBOL, 'storage': 'sqlite'}
        informant = Informant(services, config)
        orderbook = Orderbook(services, config)
        wallet = Wallet(services, config)
        async with informant, orderbook, wallet:
            fees = informant.get_fees(exchange=EXCHANGE, symbol=SYMBOL)
            filters = informant.get_filters(exchange=EXCHANGE, symbol=SYMBOL)

            if SIDE is Side.BUY:
                market_fills = orderbook.find_market_order_asks(
                    exchange=EXCHANGE,
                    symbol=SYMBOL,
                    quote=QUOTE,
                    fees=fees,
                    filters=filters)
                res = await orderbook.buy_limit_at_spread(
                    exchange=EXCHANGE,
                    symbol=SYMBOL,
                    quote=QUOTE,
                    filters=filters)
            else:
                market_fills = orderbook.find_market_order_bids(
                    exchange=EXCHANGE,
                    symbol=SYMBOL,
                    base=BASE,
                    fees=fees,
                    filters=filters)
                res = await orderbook.sell_limit_at_spread(
                    exchange=EXCHANGE,
                    symbol=SYMBOL,
                    base=BASE,
                    filters=filters)

            logging.info(res)
            logging.info(f'total size: {res.fills.total_size}')
            logging.info(f'total quote: {res.fills.total_quote}')
            logging.info(f'in case of market order total size: {market_fills.total_size}')
            logging.info(f'in case of market order total quote: {market_fills.total_quote}')

    logging.info('Done!')


logging.basicConfig(
    handlers=[logging.StreamHandler(stream=sys.stdout)],
    level=LOG_LEVEL)
asyncio.run(main())
