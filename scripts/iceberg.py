import argparse
import asyncio
import logging
from decimal import Decimal
from typing import Awaitable, Callable

from juno import BadOrder, Fill, Side, brokers, exchanges
from juno.brokers import Limit
from juno.common import OrderResult
from juno.components import Informant, Orderbook, User
from juno.config import from_env, init_instance
from juno.storages import SQLite
from juno.utils import get_module_type, unpack_assets

parser = argparse.ArgumentParser()
parser.add_argument('side', nargs='?', type=lambda s: Side[s.upper()])
parser.add_argument('symbol', nargs='?')
parser.add_argument('size', nargs='?', type=Decimal)
parser.add_argument('chunk_size', nargs='?', type=Decimal)
parser.add_argument('-e', '--exchange', default='binance')
parser.add_argument('-a', '--account', default='spot')
args = parser.parse_args()


async def main() -> None:
    exchange = init_instance(get_module_type(exchanges, args.exchange), from_env())
    sqlite = SQLite()
    informant = Informant(storage=sqlite, exchanges=[exchange])
    user = User(exchanges=[exchange])
    orderbook = Orderbook(exchanges=[exchange])
    broker = Limit(informant, orderbook, user)
    async with exchange, informant, orderbook, user:
        await transact_symbol(informant, orderbook, user, broker, args.symbol)


async def transact_symbol(
    informant: Informant,
    orderbook: Orderbook,
    user: User,
    broker: brokers.Broker,
    symbol: str,
) -> None:
    base_asset, _ = unpack_assets(symbol)
    fees, filters = informant.get_fees_filters(args.exchange, symbol)

    size = args.size
    chunk_size = args.chunk_size
    find_market_fills_fn: Callable[..., list[Fill]]
    broker_fn: Callable[..., Awaitable[OrderResult]]

    orderbook_sync = orderbook.sync(exchange=args.exchange, symbol=symbol)
    user_stream_orders = user.connect_stream_orders(
        exchange=args.exchange, account=args.account, symbol=symbol
    )
    # We open user order stream so that the broker wouldn't close and reopen it on every
    # transaction.
    async with orderbook_sync as book, user_stream_orders:
        if args.side is Side.BUY:
            logging.info(f'buying {size} {base_asset} with limit broker in chunks of {chunk_size}')
            find_market_fills_fn = book.find_order_asks
            broker_fn = broker.buy
        else:
            logging.info(
                f'selling {size} {base_asset} with limit broker in chunks of {chunk_size}'
            )
            find_market_fills_fn = book.find_order_bids
            broker_fn = broker.sell

        market_fills = find_market_fills_fn(
            size=size,
            fee_rate=fees.maker,
            filters=filters,
        )

        fills = []
        num_chunks = 0

        while size > 0:
            logging.info(f'transacting {symbol} chunk number {num_chunks + 1}')
            transact_size = min(size, chunk_size)
            try:
                res = await broker_fn(
                    exchange=args.exchange,
                    account=args.account,
                    symbol=symbol,
                    size=transact_size,
                    test=False,
                )
            except BadOrder as e:
                logging.warning(f'unable to transact last chunk: {e}')
                break
            size -= Fill.total_size(res.fills)
            fills.extend(res.fills)
            num_chunks += 1

    logging.info(f'{args.account} {args.side.name} {symbol}')
    logging.info(f'{num_chunks} chunks executed')
    logging.info(f'total size: {Fill.total_size(fills)}')
    logging.info(f'total quote: {Fill.total_quote(fills)}')
    logging.info(f'total fee(s): {Fill.all_fees(fills)}')
    logging.info(f'in case of market order total size: {Fill.total_size(market_fills)}')
    logging.info(f'in case of market order total quote: {Fill.total_quote(market_fills)}')
    logging.info(f'in case of market order total fee(s): {Fill.all_fees(market_fills)}')


asyncio.run(main())
