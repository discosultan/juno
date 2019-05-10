import asyncio
import logging
import os
import sys

from juno import OrderType, Side
from juno.components import Informant, Orderbook, Wallet
from juno.exchanges import Binance
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

            filters = informant.get_filters(exchange, SYMBOL)
            logging.info(filters)

            base_asset, quote_asset = unpack_symbol(SYMBOL)
            if SIDE == Side.BUY:
                balance = wallet.get_balance(exchange, quote_asset)
                logging.info(balance)
                fills = orderbook.find_market_order_asks(
                    exchange=exchange,
                    symbol=SYMBOL,
                    quote=balance.available,
                    fees=fees,
                    filters=filters)
            else:
                balance = wallet.get_balance(exchange, base_asset)
                logging.info(balance)
                fills = orderbook.find_market_order_bids(
                    exchange=exchange,
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
