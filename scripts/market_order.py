import asyncio
import logging
import sys
from decimal import Decimal
from typing import Optional

from juno import Fill, Side
from juno.brokers import Market
from juno.components import Informant, Orderbook, Wallet
from juno.config import from_env, init_instance
from juno.exchanges import Binance
from juno.storages import Memory, SQLite
from juno.utils import unpack_symbol

SIDE = Side.BUY
EXCHANGE = 'binance'
SYMBOL = 'eth-btc'
BASE_ASSET, QUOTE_ASSET = unpack_symbol(SYMBOL)
QUOTE: Optional[Decimal] = Decimal('0.005')
# QUOTE = None
# BASE: Optional[Decimal] = Decimal('0.2')
BASE = None
TEST = True

if len(sys.argv) > 1:
    SIDE = Side[sys.argv[1].upper()]


async def main() -> None:
    binance = init_instance(Binance, from_env())
    exchanges = [binance]
    memory = Memory()
    sqlite = SQLite()
    informant = Informant(storage=sqlite, exchanges=exchanges)
    orderbook = Orderbook(exchanges=exchanges, config={'symbol': SYMBOL})
    wallet = Wallet(exchanges=exchanges)
    market = Market(informant, orderbook, exchanges)
    async with binance, memory, informant, orderbook, wallet:
        base = BASE if BASE is not None else wallet.get_balance(EXCHANGE, BASE_ASSET).available
        quote = QUOTE if QUOTE is not None else wallet.get_balance(EXCHANGE, QUOTE_ASSET).available
        logging.info(f'base: {base} {BASE_ASSET}; quote: {quote} {QUOTE_ASSET}')
        if SIDE is Side.BUY:
            res = await market.buy_by_quote(
                exchange=EXCHANGE, symbol=SYMBOL, quote=quote, test=TEST
            )
        else:
            res = await market.sell(exchange=EXCHANGE, symbol=SYMBOL, size=base, test=TEST)

        logging.info(res)
        logging.info(f'{SIDE} {SYMBOL}')
        logging.info(f'total size: {Fill.total_size(res.fills)}')
        logging.info(f'total quote: {Fill.total_quote(res.fills)}')


asyncio.run(main())
