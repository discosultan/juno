import asyncio
import logging
import sys
from decimal import Decimal
from typing import Optional

from juno import Fill, Side, exchanges
from juno.brokers import Limit
from juno.components import Informant, Orderbook, Wallet
from juno.config import from_env, init_instance
from juno.storages import Memory, SQLite
from juno.utils import unpack_symbol

# SIDE = Side.BUY
# EXCHANGE_TYPE = exchanges.Coinbase
# SYMBOL = 'btc-eur'
# QUOTE: Optional[Decimal] = Decimal('10.0')
# BASE = None

SIDE = Side.BUY
EXCHANGE_TYPE = exchanges.Binance
SYMBOL = 'eth-btc'
QUOTE: Optional[Decimal] = Decimal('0.005')
BASE = None

if len(sys.argv) > 1:
    SIDE = Side[sys.argv[1].upper()]


async def main() -> None:
    base_asset, quote_asset = unpack_symbol(SYMBOL)
    exchange = init_instance(EXCHANGE_TYPE, from_env())
    exchanges = [exchange]
    exchange_name = EXCHANGE_TYPE.__name__.lower()
    memory = Memory()
    sqlite = SQLite()
    informant = Informant(storage=sqlite, exchanges=exchanges)
    orderbook = Orderbook(exchanges=exchanges, config={'symbol': SYMBOL})
    wallet = Wallet(exchanges=exchanges)
    limit = Limit(informant, orderbook, exchanges)
    async with exchange, memory, informant, orderbook, wallet:
        fees, filters = informant.get_fees_filters(exchange_name, SYMBOL)
        base = (
            BASE if BASE is not None else wallet.get_balance(exchange_name, base_asset).available
        )
        quote = (
            QUOTE if QUOTE is not None
            else wallet.get_balance(exchange_name, quote_asset).available
        )
        logging.info(f'base: {base} {base_asset}; quote: {quote} {quote_asset}')
        if SIDE is Side.BUY:
            market_fills = orderbook.find_order_asks_by_quote(
                exchange=exchange_name, symbol=SYMBOL, quote=quote, fee_rate=fees.maker,
                filters=filters
            )
            res = await limit.buy_by_quote(
                exchange=exchange_name, symbol=SYMBOL, quote=quote, test=False
            )
        else:
            market_fills = orderbook.find_order_bids(
                exchange=exchange_name, symbol=SYMBOL, size=base, fee_rate=fees.maker,
                filters=filters
            )
            res = await limit.sell(exchange=exchange_name, symbol=SYMBOL, size=base, test=False)

        logging.info(res)
        logging.info(f'{SIDE.name} {SYMBOL}')
        logging.info(f'total size: {Fill.total_size(res.fills)}')
        logging.info(f'total quote: {Fill.total_quote(res.fills)}')
        logging.info(f'total fee: {Fill.total_fee(res.fills)}')
        logging.info(f'in case of market order total size: {Fill.total_size(market_fills)}')
        logging.info(f'in case of market order total quote: {Fill.total_quote(market_fills)}')
        logging.info(f'in case of market order total fee: {Fill.total_fee(market_fills)}')


asyncio.run(main())
