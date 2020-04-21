import asyncio
import logging
import sys
from decimal import Decimal
from typing import Optional

from juno import Fill, Side, brokers, exchanges
from juno.components import Informant, Orderbook, Wallet
from juno.config import from_env, init_instance
from juno.storages import SQLite
from juno.utils import unpack_symbol

MARKET_BROKER_TYPE = brokers.Market2
SIDE = Side.BUY
EXCHANGE_TYPE = exchanges.Coinbase
SYMBOL = 'btc-eur'
QUOTE: Optional[Decimal] = Decimal('10.0')
# QUOTE = None
# BASE: Optional[Decimal] = Decimal('0.2')
BASE = None
TEST = False

# MARKET_BROKER_TYPE = brokers.Market2
# SIDE = Side.BUY
# EXCHANGE_TYPE = exchanges.Binance
# SYMBOL = 'eth-btc'
# QUOTE: Optional[Decimal] = Decimal('0.005')
# # QUOTE = None
# # BASE: Optional[Decimal] = Decimal('0.2')
# BASE = None
# TEST = False

if len(sys.argv) > 1:
    SIDE = Side[sys.argv[1].upper()]


async def main() -> None:
    base_asset, quote_asset = unpack_symbol(SYMBOL)
    exchange = init_instance(EXCHANGE_TYPE, from_env())
    exchange_name = EXCHANGE_TYPE.__name__.lower()
    exchanges = [exchange]
    sqlite = SQLite()
    informant = Informant(storage=sqlite, exchanges=exchanges)
    orderbook = Orderbook(exchanges=exchanges, config={'symbol': SYMBOL})
    wallet = Wallet(exchanges=exchanges)
    market = MARKET_BROKER_TYPE(informant, orderbook, exchanges)
    async with exchange, informant, orderbook, wallet:
        base = (
            BASE if BASE is not None else wallet.get_balance(exchange_name, base_asset).available
        )
        quote = (
            QUOTE if QUOTE is not None
            else wallet.get_balance(exchange_name, quote_asset).available
        )
        logging.info(f'base: {base} {base_asset}; quote: {quote} {quote_asset}')
        if SIDE is Side.BUY:
            res = await market.buy_by_quote(
                exchange=exchange_name, symbol=SYMBOL, quote=quote, test=TEST
            )
        else:
            res = await market.sell(exchange=exchange_name, symbol=SYMBOL, size=base, test=TEST)

        logging.info(res)
        logging.info(f'{SIDE.name} {SYMBOL}')
        logging.info(f'total size: {Fill.total_size(res.fills)}')
        logging.info(f'total quote: {Fill.total_quote(res.fills)}')
        logging.info(f'total fee: {Fill.total_fee(res.fills)}')


asyncio.run(main())
