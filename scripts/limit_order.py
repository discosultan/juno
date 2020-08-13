import argparse
import asyncio
import logging
from decimal import Decimal

from juno import Fill, Side
from juno.brokers import Limit
from juno.components import Informant, Orderbook, Wallet
from juno.config import from_env, init_instance
from juno.exchanges import Binance, Exchange
from juno.storages import Memory, SQLite
from juno.utils import unpack_symbol

parser = argparse.ArgumentParser()
parser.add_argument('side', nargs='?', type=lambda s: Side[s.upper()], default=Side.BUY)
parser.add_argument('symbols', nargs='?', type=lambda s: s.split(','), default='eth-btc')
parser.add_argument(
    'value', nargs='?', type=Decimal, default=None, help='if buy, quote; otherwise base size'
)
parser.add_argument('account', nargs='?', default='spot')
args = parser.parse_args()


async def main() -> None:
    exchange = init_instance(Binance, from_env())
    memory = Memory()
    sqlite = SQLite()
    informant = Informant(storage=sqlite, exchanges=[exchange])
    orderbook = Orderbook(exchanges=[exchange])
    wallet = Wallet(exchanges=[exchange])
    limit = Limit(informant, orderbook, [exchange])
    async with exchange, memory, informant, orderbook, wallet:
        await asyncio.gather(
            *(transact_symbol(
                informant, orderbook, wallet, exchange, limit, s
            ) for s in args.symbols)
        )


async def transact_symbol(
    informant: Informant,
    orderbook: Orderbook,
    wallet: Wallet,
    exchange: Exchange,
    limit: Limit,
    symbol: str,
) -> None:
    base_asset, quote_asset = unpack_symbol(symbol)
    fees, filters = informant.get_fees_filters('binance', symbol)
    available_base = wallet.get_balance('binance', base_asset, account=args.account).available
    available_quote = wallet.get_balance('binance', quote_asset, account=args.account).available
    value = args.value if args.value is not None else (
        available_quote if args.side is Side.BUY else available_base
    )
    logging.info(
        f'available base: {available_base} {base_asset}; available quote: {available_quote} '
        f'{quote_asset}')
    if args.side is Side.BUY:
        market_fills = orderbook.find_order_asks_by_quote(
            exchange='binance', symbol=symbol, quote=value, fee_rate=fees.maker,
            filters=filters
        )
        res = await limit.buy(
            exchange='binance', symbol=symbol, quote=value, account=args.account, test=False,
        )
    else:
        market_fills = orderbook.find_order_bids(
            exchange='binance', symbol=symbol, size=value, fee_rate=fees.maker,
            filters=filters
        )
        res = await limit.sell(
            exchange='binance', symbol=symbol, size=value, account=args.account, test=False
        )

    logging.info(res)
    logging.info(f'{args.account} {args.side.name} {symbol}')
    logging.info(f'total size: {Fill.total_size(res.fills)}')
    logging.info(f'total quote: {Fill.total_quote(res.fills)}')
    logging.info(f'total fee: {Fill.total_fee(res.fills)}')
    logging.info(f'in case of market order total size: {Fill.total_size(market_fills)}')
    logging.info(f'in case of market order total quote: {Fill.total_quote(market_fills)}')
    logging.info(f'in case of market order total fee: {Fill.total_fee(market_fills)}')


asyncio.run(main())
