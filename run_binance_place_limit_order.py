import asyncio
import logging
import os
import sys
from decimal import Decimal

from juno import OrderType, Side, TimeInForce
from juno.components import Informant, Orderbook, Wallet
from juno.exchanges import Binance
from juno.math import adjust_price, adjust_size
from juno.storages import Memory, SQLite
from juno.utils import unpack_symbol

TEST = False
SIDE = Side.BUY
SYMBOL = 'ada-btc'
CLIENT_ID = 'foo'
LOG_LEVEL = 'DEBUG'


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
            asks = orderbook.list_asks(exchange, SYMBOL)
            bids = orderbook.list_bids(exchange, SYMBOL)

            if SIDE is Side.BUY:
                balance = wallet.get_balance(exchange, quote_asset)
                best_price, _ = bids[0]
                price = best_price * Decimal('0.5')  # way shittier, so we dont fill
                size = balance.available / price
            else:
                balance = wallet.get_balance(exchange, base_asset)
                best_price, _ = asks[0]
                price = best_price * Decimal('1.5')  # way shittier, so we dont fill
                size = balance.available

            price = adjust_price(price, symbol_info.min_price, symbol_info.max_price,
                                 symbol_info.price_step)
            size = adjust_size(size, symbol_info.min_size, symbol_info.max_size,
                               symbol_info.size_step)

            logging.info(f'Adjusted price: {price}, size: {size}')

            if price == 0:
                logging.error('Invalid price! Quitting!')
                return

            if size == 0:
                logging.error('Not enough balance! Quitting!')
                return

            res = await binance.place_order(
                symbol=SYMBOL,
                side=SIDE,
                type_=OrderType.LIMIT,
                price=price,
                size=size,
                time_in_force=TimeInForce.GTC,
                client_id=CLIENT_ID,
                test=TEST)
            logging.info(res)
    logging.info('Done!')


logging.basicConfig(
    handlers=[logging.StreamHandler(stream=sys.stdout)],
    level=LOG_LEVEL)
asyncio.run(main())
