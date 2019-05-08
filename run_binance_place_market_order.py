import asyncio
import logging
import os
import sys

from juno import OrderType, Side
from juno.components import Informant, Orderbook, Wallet
from juno.exchanges import Binance
from juno.math import adjust_size
from juno.storages import Memory, SQLite
from juno.utils import unpack_symbol

TEST = True
SIDE = Side.SELL
SYMBOL = 'ada-btc'


async def main() -> None:
    binance = Binance(os.environ['JUNO__BINANCE__API_KEY'],
                      os.environ['JUNO__BINANCE__SECRET_KEY'])
    memory = Memory()
    sqlite = SQLite()
    async with binance, memory, sqlite:
        exchange = 'binance'
        services = {'binance': binance, 'memory': memory, 'sqlite': sqlite}
        config = {'symbol': SYMBOL, 'storage': 'sqlite'}
        informant = Informant(services, config)
        orderbook = Orderbook(services, config)
        wallet = Wallet(services, config)
        async with informant, orderbook, wallet:
            fees = informant.get_fees(exchange, SYMBOL)
            logging.info(fees)

            symbol_info = informant.get_symbol_info(exchange, SYMBOL)
            logging.info(symbol_info)

            base_asset, quote_asset = unpack_symbol(SYMBOL)
            if SIDE == Side.BUY:
                balance = wallet.get_balance(exchange, quote_asset)
                logging.info(balance)
                fills = orderbook.find_market_order_asks(
                    exchange, SYMBOL, balance.available, symbol_info, fees)
            else:
                balance = wallet.get_balance(exchange, base_asset)
                logging.info(balance)
                fills = orderbook.find_market_order_bids(
                    exchange, SYMBOL, balance.available, symbol_info, fees)

            logging.info(f'Size from orderbook: {fills.total_size}')
            size = adjust_size(fills.total_size, symbol_info.min_size, symbol_info.max_size,
                               symbol_info.size_step)
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
