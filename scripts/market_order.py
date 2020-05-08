import argparse
import asyncio
import logging
from decimal import Decimal
from typing import Optional

from juno import Fill, Side, brokers, exchanges
from juno.components import Informant, Orderbook, Wallet
from juno.config import from_env, init_instance
from juno.storages import SQLite
from juno.utils import unpack_symbol

MARKET_BROKER_TYPE = brokers.Market2
EXCHANGE_TYPE = exchanges.Coinbase
QUOTE: Optional[Decimal] = Decimal('10.0')
BASE = None
TEST = False

# MARKET_BROKER_TYPE = brokers.Market2
# EXCHANGE_TYPE = exchanges.Binance
# QUOTE: Optional[Decimal] = Decimal('0.005')
# BASE = None
# TEST = False

parser = argparse.ArgumentParser()
parser.add_argument('side', nargs='?', type=lambda s: Side[s.upper()], default=Side.BUY)
parser.add_argument('symbol', nargs='?', default='eth-btc')
args = parser.parse_args()


async def main() -> None:
    base_asset, quote_asset = unpack_symbol(args.symbol)
    exchange = init_instance(EXCHANGE_TYPE, from_env())
    exchange_name = EXCHANGE_TYPE.__name__.lower()
    exchanges = [exchange]
    sqlite = SQLite()
    informant = Informant(storage=sqlite, exchanges=exchanges)
    orderbook = Orderbook(exchanges=exchanges, config={'symbol': args.symbol})
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
        if args.side is Side.BUY:
            res = await market.buy_by_quote(
                exchange=exchange_name, symbol=args.symbol, quote=quote, test=TEST
            )
        else:
            res = await market.sell(
                exchange=exchange_name, symbol=args.symbol, size=base, test=TEST
            )

        logging.info(res)
        logging.info(f'{args.side.name} {args.symbol}')
        logging.info(f'total size: {Fill.total_size(res.fills)}')
        logging.info(f'total quote: {Fill.total_quote(res.fills)}')
        logging.info(f'total fee: {Fill.total_fee(res.fills)}')


asyncio.run(main())
