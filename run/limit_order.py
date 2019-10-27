import asyncio
import logging
import os
import sys
from decimal import Decimal
from typing import List, Optional

from juno import Side
from juno.brokers import Limit, Market
from juno.components import Informant, Orderbook, Wallet
from juno.exchanges import Binance, Exchange
from juno.logging import create_handlers
from juno.storages import Memory, SQLite
from juno.utils import unpack_symbol

SIDE = Side.SELL
EXCHANGE = 'binance'
SYMBOL = 'eth-btc'
BASE_ASSET, QUOTE_ASSET = unpack_symbol(SYMBOL)
LOG_LEVEL = 'INFO'
QUOTE: Optional[Decimal] = Decimal('0.005')
QUOTE = None
BASE: Optional[Decimal] = Decimal('0.2')
BASE = None

if len(sys.argv) > 1:
    SIDE = Side[sys.argv[1].upper()]


async def main() -> None:
    binance = Binance(
        os.environ['JUNO__BINANCE__API_KEY'], os.environ['JUNO__BINANCE__SECRET_KEY']
    )
    exchanges: List[Exchange] = [binance]
    memory = Memory()
    sqlite = SQLite()
    informant = Informant(storage=sqlite, exchanges=exchanges)
    orderbook = Orderbook(exchanges=exchanges, config={'symbol': SYMBOL})
    wallet = Wallet(exchanges=exchanges)
    market = Market(informant, orderbook, exchanges)
    limit = Limit(informant, orderbook, exchanges)
    async with binance, memory, informant, orderbook, wallet:
        base = BASE if BASE is not None else wallet.get_balance(EXCHANGE, BASE_ASSET).available
        quote = QUOTE if QUOTE is not None else wallet.get_balance(EXCHANGE, QUOTE_ASSET).available
        logging.info(f'base: {base} {BASE_ASSET}; quote: {quote} {QUOTE_ASSET}')
        if SIDE is Side.BUY:
            market_fills = market.find_order_asks(exchange=EXCHANGE, symbol=SYMBOL, quote=quote)
            res = await limit.buy(exchange=EXCHANGE, symbol=SYMBOL, quote=quote, test=False)
        else:
            market_fills = market.find_order_bids(exchange=EXCHANGE, symbol=SYMBOL, base=base)
            res = await limit.sell(exchange=EXCHANGE, symbol=SYMBOL, base=base, test=False)

        logging.info(res)
        logging.info(f'{SIDE} {SYMBOL}')
        logging.info(f'total size: {res.fills.total_size}')
        logging.info(f'total quote: {res.fills.total_quote}')
        logging.info(f'in case of market order total size: {market_fills.total_size}')
        logging.info(f'in case of market order total quote: {market_fills.total_quote}')

    logging.info('Done!')


logging.basicConfig(handlers=create_handlers('colored', ['stdout']), level=LOG_LEVEL)
asyncio.run(main())
