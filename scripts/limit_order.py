import argparse
import asyncio
import logging

from juno import Fill, Side, exchanges
from juno.brokers import Limit
from juno.components import Informant, Orderbook, Wallet
from juno.config import from_env, init_instance
from juno.storages import Memory, SQLite
from juno.utils import unpack_symbol

EXCHANGE_TYPE = exchanges.Binance
SIDE = 'buy'
SYMBOL = 'eth-btc'

parser = argparse.ArgumentParser()
parser.add_argument('side', nargs='?', default=SIDE)
parser.add_argument('symbol', nargs='?', default=SYMBOL)
parser.add_argument('value', nargs='?', default=None, help='if buy, quote; otherwise base size')
args = parser.parse_args()

side = Side[args.side.upper()]


async def main() -> None:
    base_asset, quote_asset = unpack_symbol(args.symbol)
    exchange = init_instance(EXCHANGE_TYPE, from_env())
    exchanges = [exchange]
    exchange_name = EXCHANGE_TYPE.__name__.lower()
    memory = Memory()
    sqlite = SQLite()
    informant = Informant(storage=sqlite, exchanges=exchanges)
    orderbook = Orderbook(exchanges=exchanges, config={'symbol': args.symbol})
    wallet = Wallet(exchanges=exchanges)
    limit = Limit(informant, orderbook, exchanges)
    async with exchange, memory, informant, orderbook, wallet:
        fees, filters = informant.get_fees_filters(exchange_name, args.symbol)
        available_base = wallet.get_balance(exchange_name, base_asset).available
        available_quote = wallet.get_balance(exchange_name, quote_asset).available
        value = args.value if args.value is not None else (
            available_quote if side is Side.BUY else available_base
        )
        logging.info(
            f'available base: {available_base} {base_asset}; available quote: {available_quote} '
            f'{quote_asset}')
        if side is Side.BUY:
            market_fills = orderbook.find_order_asks_by_quote(
                exchange=exchange_name, symbol=args.symbol, quote=value, fee_rate=fees.maker,
                filters=filters
            )
            res = await limit.buy_by_quote(
                exchange=exchange_name, symbol=args.symbol, quote=value, test=False
            )
        else:
            market_fills = orderbook.find_order_bids(
                exchange=exchange_name, symbol=args.symbol, size=value, fee_rate=fees.maker,
                filters=filters
            )
            res = await limit.sell(
                exchange=exchange_name, symbol=args.symbol, size=value, test=False
            )

        logging.info(res)
        logging.info(f'{side.name} {args.symbol}')
        logging.info(f'total size: {Fill.total_size(res.fills)}')
        logging.info(f'total quote: {Fill.total_quote(res.fills)}')
        logging.info(f'total fee: {Fill.total_fee(res.fills)}')
        logging.info(f'in case of market order total size: {Fill.total_size(market_fills)}')
        logging.info(f'in case of market order total quote: {Fill.total_quote(market_fills)}')
        logging.info(f'in case of market order total fee: {Fill.total_fee(market_fills)}')


asyncio.run(main())
