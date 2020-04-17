import asyncio
import logging
from typing import List

from juno import Fill, OrderType, Side
from juno.brokers import Market
from juno.components import Informant, Orderbook, Wallet
from juno.config import from_env, init_instance
from juno.exchanges import Binance, Exchange
from juno.storages import Memory, SQLite
from juno.utils import unpack_symbol

EXCHANGE_TYPE = Binance
TEST = False
SIDE = Side.BUY
SYMBOL = 'btc-eur'


async def main() -> None:
    exchange = init_instance(EXCHANGE_TYPE, from_env())
    exchange_name = EXCHANGE_TYPE.__name__.lower()
    exchanges: List[Exchange] = [exchange]
    memory = Memory()
    sqlite = SQLite()
    informant = Informant(storage=sqlite, exchanges=exchanges)
    orderbook = Orderbook(exchanges=exchanges, config={'symbol': SYMBOL})
    wallet = Wallet(exchanges=exchanges)
    market = Market(informant, orderbook, exchanges)
    async with exchange, memory, informant, orderbook, wallet:
        _fees, filters = informant.get_fees_filters(exchange_name, SYMBOL)

        base_asset, quote_asset = unpack_symbol(SYMBOL)
        if SIDE is Side.BUY:
            balance = wallet.get_balance(exchange_name, quote_asset)
            logging.info(balance)
            fills = market.find_order_asks_by_quote(
                exchange=exchange_name, symbol=SYMBOL, quote=balance.available
            )
        else:
            balance = wallet.get_balance(exchange_name, base_asset)
            logging.info(balance)
            fills = market.find_order_bids(
                exchange=exchange_name, symbol=SYMBOL, size=balance.available
            )

        size = Fill.total_size(fills)
        logging.info(f'Size from orderbook: {size}')
        size = filters.size.round_down(size)
        logging.info(f'Adjusted size: {size}')

        logging.info(f'Unadjusted fee: {Fill.total_fee(fills)}')

        if size == 0:
            logging.error('Not enough balance! Quitting!')
            return

        logging.info(fills)

        res = await exchange.place_order(
            symbol=SYMBOL, side=SIDE, type_=OrderType.MARKET, size=size, test=TEST
        )
        logging.info(res)


asyncio.run(main())
