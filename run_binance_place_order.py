import asyncio
import logging
import os
from decimal import Decimal

from juno import OrderType, Side
from juno.components import Informant, Orderbook, Wallet
from juno.exchanges import Binance
from juno.math import adjust_size
from juno.storages import Memory
from juno.utils import unpack_symbol


async def main() -> None:
    async with Binance(os.environ['JUNO__BINANCE__API_KEY'],
                       os.environ['JUNO__BINANCE__SECRET_KEY']) as binance:
        exchange = 'binance'
        services = {'binance': binance, 'memory': Memory()}
        symbol = 'ada-btc'
        config = {'symbol': symbol, 'storage': 'memory'}
        informant = Informant(services, config)
        orderbook = Orderbook(services, config)
        wallet = Wallet(services, config)
        async with informant, orderbook, wallet:
            fees = informant.get_fees(exchange)
            logging.info(fees)

            symbol_info = informant.get_symbol_info(exchange, symbol)
            logging.info(symbol_info)

            _, quote_asset = unpack_symbol(symbol)
            quote_balance = wallet.get_balance(exchange, quote_asset)
            logging.info(quote_balance)

            quote = quote_balance.available
            asks = orderbook.find_market_order_asks(exchange, symbol, quote, symbol_info, fees)

            logging.info(f'Size from orderbook: {asks.total_size}')
            size = adjust_size(asks.total_size, symbol_info.min_size, symbol_info.max_size,
                               symbol_info.size_step)
            logging.info(f'Adjusted size: {size}')

            if size == Decimal(0):
                logging.critical('Not enough balance! Quitting!')
                return

            res = await binance.place_order(
                symbol=symbol,
                side=Side.BUY,
                type_=OrderType.MARKET,
                size=size,
                test=False)
            logging.info(res)


logging.basicConfig(level='DEBUG')
asyncio.run(main())
