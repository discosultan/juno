import argparse
import asyncio
import logging
from decimal import Decimal

from juno import Balance, Fill, Side, brokers, exchanges
from juno.components import Informant, Orderbook, User
from juno.config import from_env, init_instance
from juno.storages import SQLite
from juno.utils import get_module_type, unpack_assets

parser = argparse.ArgumentParser()
parser.add_argument('side', nargs='?', type=lambda s: Side[s.upper()])
parser.add_argument('symbols', nargs='?', type=lambda s: s.split(','))
parser.add_argument('-b', '--broker', default='limit')
parser.add_argument('-e', '--exchange', default='binance')
parser.add_argument('-a', '--account', default='spot')
parser.add_argument('-s', '--size', type=Decimal, default=None)
parser.add_argument('-q', '--quote', type=Decimal, default=None)
parser.add_argument(
    '-t',
    '--test',
    action='store_true',
    default=False,
)
parser.add_argument(
    '--ensure-size',
    action='store_true',
    default=False,
)
args = parser.parse_args()


async def main() -> None:
    assert not (args.size and args.quote)

    exchange = init_instance(get_module_type(exchanges, args.exchange), from_env())
    sqlite = SQLite()
    informant = Informant(storage=sqlite, exchanges=[exchange])
    user = User(exchanges=[exchange])
    orderbook = Orderbook(exchanges=[exchange])
    broker = get_module_type(brokers, args.broker)(informant, orderbook, user)
    async with exchange, informant, orderbook, user:
        balances = (await user.map_balances(
            exchange=args.exchange, accounts=[args.account]
        ))[args.account]
        await asyncio.gather(
            *(transact_symbol(informant, orderbook, broker, balances, s) for s in args.symbols)
        )


async def transact_symbol(
    informant: Informant,
    orderbook: Orderbook,
    broker: brokers.Broker,
    balances: dict[str, Balance],
    symbol: str,
) -> None:
    base_asset, quote_asset = unpack_assets(symbol)
    fees, filters = informant.get_fees_filters(args.exchange, symbol)

    available_base = balances.get(base_asset, Balance.zero()).available
    available_quote = balances.get(quote_asset, Balance.zero()).available
    logging.info(
        f'available base: {available_base} {base_asset}; quote: {available_quote} '
        f'{quote_asset}'
    )

    size = args.size
    quote = args.quote
    if not size and not quote:
        if args.side is Side.BUY:
            quote = available_quote
        else:
            size = available_base
    logging.info(f'using base: {size} {base_asset}; quote: {quote} {quote_asset}')

    async with orderbook.sync(args.exchange, symbol) as book:
        if args.side is Side.BUY:
            market_fills = book.find_order_asks(
                size=size,
                quote=quote,
                fee_rate=fees.maker,
                filters=filters,
            )
            res = await broker.buy(
                exchange=args.exchange,
                account=args.account,
                symbol=symbol,
                quote=quote,
                size=size,
                test=args.test,
                ensure_size=args.ensure_size,
            )
        else:
            market_fills = book.find_order_bids(
                size=size,
                quote=quote,
                fee_rate=fees.maker,
                filters=filters,
            )
            res = await broker.sell(
                exchange=args.exchange,
                account=args.account,
                symbol=symbol,
                size=size,
                test=args.test,
            )

    logging.info(res)
    logging.info(f'{args.account} {args.side.name} {symbol}')
    logging.info(f'total size: {Fill.total_size(res.fills)}')
    logging.info(f'total quote: {Fill.total_quote(res.fills)}')
    logging.info(f'total fee(s): {Fill.all_fees(res.fills)}')
    logging.info(f'in case of market order total size: {Fill.total_size(market_fills)}')
    logging.info(f'in case of market order total quote: {Fill.total_quote(market_fills)}')
    logging.info(f'in case of market order total fee(s): {Fill.all_fees(market_fills)}')


asyncio.run(main())
