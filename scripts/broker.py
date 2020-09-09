import argparse
import asyncio
import logging
from decimal import Decimal
from typing import Dict

from juno import Balance, Fill, Side, brokers, exchanges
from juno.components import Informant, Orderbook, Wallet
from juno.config import from_env, init_instance
from juno.storages import SQLite
from juno.utils import get_module_type, unpack_symbol

parser = argparse.ArgumentParser()
parser.add_argument('side', nargs='?', type=lambda s: Side[s.upper()], default=Side.BUY)
parser.add_argument('symbols', nargs='?', type=lambda s: s.split(','), default='eth-btc')
parser.add_argument('-b', '--broker', default='limit')
parser.add_argument('-e', '--exchange', default='binance')
parser.add_argument('-a', '--account', default='spot')
parser.add_argument('-s', '--size', type=Decimal, default=None)
parser.add_argument('-q', '--quote', type=Decimal, default=None)
parser.add_argument(
    '-t', '--test',
    action='store_true',
    default=False,
)
args = parser.parse_args()


async def main() -> None:
    assert not (args.size and args.quote)

    exchange = init_instance(get_module_type(exchanges, args.exchange), from_env())
    sqlite = SQLite()
    informant = Informant(storage=sqlite, exchanges=[exchange])
    wallet = Wallet(exchanges=[exchange])
    orderbook = Orderbook(exchanges=[exchange])
    broker = get_module_type(brokers, args.broker)(informant, orderbook)
    async with exchange, informant, orderbook, wallet:
        balances = (await wallet.map_balances(
            exchange=args.exchange, accounts=[args.account]
        ))[args.account]
        await asyncio.gather(
            *(transact_symbol(
                informant, orderbook, exchange, broker, balances, s
            ) for s in args.symbols)
        )


async def transact_symbol(
    informant: Informant,
    orderbook: Orderbook,
    exchange: exchanges.Exchange,
    broker: brokers.Broker,
    balances: Dict[str, Balance],
    symbol: str,
) -> None:
    base_asset, quote_asset = unpack_symbol(symbol)
    fees, filters = informant.get_fees_filters(args.exchange, symbol)

    available_base = balances[base_asset].available
    available_quote = balances[quote_asset].available
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

    if args.side is Side.BUY:
        market_fills = orderbook.find_order_asks(
            exchange=args.exchange,
            symbol=symbol,
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
        )
    else:
        market_fills = orderbook.find_order_bids(
            exchange=args.exchange,
            symbol=symbol,
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
    logging.info(f'total fee: {Fill.total_fee(res.fills)}')
    logging.info(f'in case of market order total size: {Fill.total_size(market_fills)}')
    logging.info(f'in case of market order total quote: {Fill.total_quote(market_fills)}')
    logging.info(f'in case of market order total fee: {Fill.total_fee(market_fills)}')


asyncio.run(main())
