import asyncio
import logging
from typing import List

from juno import Fill, OrderType, Side
from juno.brokers import Market
from juno.components import Informant, Orderbook, Wallet
from juno.config import config_from_env, load_instance
from juno.exchanges import Binance, Exchange
from juno.storages import Memory, SQLite
from juno.utils import unpack_symbol

EXCHANGE = 'binance'
TEST = False
SIDE = Side.BUY
SYMBOL = 'ada-btc'


async def main() -> None:
    binance = load_instance(Binance, config_from_env())
    exchanges: List[Exchange] = [binance]
    memory = Memory()
    sqlite = SQLite()
    informant = Informant(storage=sqlite, exchanges=exchanges)
    orderbook = Orderbook(exchanges=exchanges, config={'symbol': SYMBOL})
    wallet = Wallet(exchanges=exchanges)
    market = Market(informant, orderbook, exchanges)
    async with binance, memory, informant, orderbook, wallet:
        _fees, filters = informant.get_fees_filters(EXCHANGE, SYMBOL)

        base_asset, quote_asset = unpack_symbol(SYMBOL)
        if SIDE is Side.BUY:
            balance = wallet.get_balance(EXCHANGE, quote_asset)
            logging.info(balance)
            fills = market.find_order_asks(
                exchange=EXCHANGE, symbol=SYMBOL, quote=balance.available
            )
        else:
            balance = wallet.get_balance(EXCHANGE, base_asset)
            logging.info(balance)
            fills = market.find_order_bids(
                exchange=EXCHANGE, symbol=SYMBOL, base=balance.available
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

        res = await binance.place_order(
            symbol=SYMBOL, side=SIDE, type_=OrderType.MARKET, size=size, test=TEST
        )
        logging.info(res)
    logging.info('done')


asyncio.run(main())
