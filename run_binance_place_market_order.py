import asyncio
import logging
import os
import sys

from juno import OrderType, Side
from juno.components import Informant, Orderbook, Wallet
from juno.exchanges import Binance
from juno.storages import Memory, SQLite
from juno.utils import unpack_symbol

EXCHANGE = 'binance'
TEST = True
SIDE = Side.SELL
SYMBOL = 'ada-btc'


async def main() -> None:
    binance = Binance(os.environ['JUNO__BINANCE__API_KEY'],
                      os.environ['JUNO__BINANCE__SECRET_KEY'])
    memory = Memory()
    sqlite = SQLite()
    async with binance, memory, sqlite:
        informant = Informant(storage=sqlite, exchanges=[binance])
        orderbook = Orderbook(exchanges=[binance], config={'symbol': SYMBOL})
        wallet = Wallet(exchanges=[binance])
        async with informant, orderbook, wallet:
            fees = informant.get_fees(EXCHANGE, SYMBOL)
            logging.info(fees)

            filters = informant.get_filters(EXCHANGE, SYMBOL)
            logging.info(filters)

            base_asset, quote_asset = unpack_symbol(SYMBOL)
            if SIDE is Side.BUY:
                balance = wallet.get_balance(EXCHANGE, quote_asset)
                logging.info(balance)
                fills = orderbook.find_market_order_asks(
                    exchange=EXCHANGE,
                    symbol=SYMBOL,
                    quote=balance.available,
                    fees=fees,
                    filters=filters)
            else:
                balance = wallet.get_balance(EXCHANGE, base_asset)
                logging.info(balance)
                fills = orderbook.find_market_order_bids(
                    exchange=EXCHANGE,
                    symbol=SYMBOL,
                    base=balance.available,
                    fees=fees,
                    filters=filters)

            logging.info(f'Size from orderbook: {fills.total_size}')
            size = filters.size.round_down(fills.total_size)
            logging.info(f'Adjusted size: {size}')

            if size == 0:
                logging.error('Not enough balance! Quitting!')
                return

            res = await binance.place_order(
                symbol=SYMBOL,
                side=SIDE,
                type_=OrderType.MARKET,
                size=size,
                test=TEST)
            logging.info(res)
    logging.info('Done!')


logging.basicConfig(
    handlers=[logging.StreamHandler(stream=sys.stdout)],
    level='INFO')
asyncio.run(main())
