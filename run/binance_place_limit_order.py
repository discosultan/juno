import asyncio
import logging
import os
import sys
from decimal import Decimal

from juno import OrderType, Side, TimeInForce
from juno.components import Informant, Orderbook, Wallet
from juno.exchanges import Binance
from juno.storages import Memory, SQLite
from juno.utils import unpack_symbol

EXCHANGE = 'binance'
TEST = False
SIDE = Side.BID
SYMBOL = 'ada-btc'
CLIENT_ID = 'foo'
LOG_LEVEL = 'DEBUG'


async def main() -> None:
    binance = Binance(
        os.environ['JUNO__BINANCE__API_KEY'], os.environ['JUNO__BINANCE__SECRET_KEY']
    )
    memory = Memory()
    sqlite = SQLite()
    async with binance, memory:
        informant = Informant(storage=sqlite, exchanges=[binance])
        orderbook = Orderbook(exchanges=[binance], config={'symbol': SYMBOL})
        wallet = Wallet(exchanges=[binance])
        async with informant, orderbook, wallet:
            filters = informant.get_filters(EXCHANGE, SYMBOL)

            base_asset, quote_asset = unpack_symbol(SYMBOL)
            asks = orderbook.list_asks(EXCHANGE, SYMBOL)
            bids = orderbook.list_bids(EXCHANGE, SYMBOL)

            if SIDE is Side.BID:
                balance = wallet.get_balance(EXCHANGE, quote_asset)
                best_price, _ = bids[0]
                price = best_price * Decimal('0.5')  # way shittier, so we dont fill
                size = balance.available / price
            else:
                balance = wallet.get_balance(EXCHANGE, base_asset)
                best_price, _ = asks[0]
                price = best_price * Decimal('1.5')  # way shittier, so we dont fill
                size = balance.available

            price = filters.price.round_down(price)
            size = filters.size.round_down(size)

            # DEBUG
            size = filters.size.min
            if SIDE is Side.BID:
                price = best_price * Decimal('1.2')  # way better, so we fill
            else:
                price = best_price * Decimal('0.8')  # way better, so we fill
            price = filters.price.round_down(price)
            size = filters.min_notional.min_size_for_price(price)
            size = filters.size.round_up(size)
            # DEBUG END

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
                test=TEST
            )
            logging.info(res)
    logging.info('Done!')


logging.basicConfig(handlers=[logging.StreamHandler(stream=sys.stdout)], level=LOG_LEVEL)
asyncio.run(main())
