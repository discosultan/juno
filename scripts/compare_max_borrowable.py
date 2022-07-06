import argparse
import asyncio
import logging
from decimal import Decimal

from juno import Interval_, Symbol_
from juno.components import Chandler, Informant, User
from juno.config import from_env, init_instance
from juno.exchanges import Binance
from juno.storages import SQLite

parser = argparse.ArgumentParser()
parser.add_argument("symbols", type=lambda s: s.split(","))
parser.add_argument("collateral", type=Decimal)
parser.add_argument("account", nargs="?", default="margin")
args = parser.parse_args()


async def main() -> None:
    exchange = init_instance(Binance, from_env())
    storage = SQLite()
    informant = Informant(storage=storage, exchanges=[exchange])
    chandler = Chandler(storage=storage, exchanges=[exchange])
    user = User(exchanges=[exchange])
    async with exchange, informant, user, chandler:
        # Note that we need to do this sequentially; because we cannot transfer duplicate amounts
        # of collateral. Also, the max amount from exchange would be incorrect.
        for symbol in args.symbols:
            await process_symbol(informant, chandler, user, symbol)


async def process_symbol(
    informant: Informant, chandler: Chandler, user: User, symbol: str
) -> None:
    exchange_amount, manual_amount = await asyncio.gather(
        max_exchange(user, symbol),
        max_manual(informant, chandler, symbol),
    )
    base_asset, _ = Symbol_.assets(symbol)
    logging.info(f"{base_asset} max borrowable: exchange={exchange_amount} manual={manual_amount}")
    if manual_amount > exchange_amount:
        logging.error("manual amount exceeds exchange amount")


async def max_exchange(user: User, symbol: str) -> Decimal:
    base_asset, quote_asset = Symbol_.assets(symbol)
    await user.transfer(
        "binance", quote_asset, args.collateral, from_account="spot", to_account=args.account
    )
    try:
        max_borrowable = await user.get_max_borrowable(
            "binance", asset=base_asset, account=args.account
        )
    finally:
        await user.transfer(
            "binance", quote_asset, args.collateral, from_account=args.account, to_account="spot"
        )
    return max_borrowable


async def max_manual(informant: Informant, chandler: Chandler, symbol: str) -> Decimal:
    candle = await chandler.get_last_candle("binance", symbol, Interval_.MIN)
    # margin_multiplier = informant.get_margin_multiplier('binance')
    margin_multiplier = 2
    _, filters = informant.get_fees_filters("binance", symbol)

    collateral_size = filters.size.round_down(args.collateral / candle.close)
    return collateral_size * (margin_multiplier - 1)


asyncio.run(main())
