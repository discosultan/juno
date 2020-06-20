import argparse
import asyncio
import logging
from decimal import Decimal

from juno import time
from juno.components import Chandler, Informant
from juno.config import from_env, init_instance
from juno.exchanges import Binance
from juno.storages import SQLite
from juno.utils import unpack_symbol

parser = argparse.ArgumentParser()
parser.add_argument('symbols', type=lambda s: s.split(','))
parser.add_argument('collateral', type=Decimal)
args = parser.parse_args()


async def main() -> None:
    exchange = init_instance(Binance, from_env())
    storage = SQLite()
    informant = Informant(storage, exchanges=[exchange])
    chandler = Chandler(storage, [exchange], informant=informant)
    async with exchange, informant:
        # Note that we need to do this sequentially; because we cannot transfer duplicate amounts
        # of collateral. Also, the max amount from exchange would be incorrect.
        for symbol in args.symbols:
            await process_symbol(exchange, informant, chandler, symbol)


async def process_symbol(
    exchange: Binance, informant: Informant, chandler: Chandler, symbol: str
) -> None:
    exchange_amount, manual_amount = await asyncio.gather(
        max_exchange(exchange, symbol),
        max_manual(informant, chandler, symbol),
    )
    base_asset, _ = unpack_symbol(symbol)
    logging.info(
        f'{base_asset} max borrowable: exchange={exchange_amount} manual={manual_amount}'
    )
    if manual_amount > exchange_amount:
        logging.error('manual amount exceeds exchange amount')


async def max_exchange(client: Binance, symbol: str) -> Decimal:
    base_asset, quote_asset = unpack_symbol(symbol)
    await client.transfer(quote_asset, args.collateral, margin=True)
    try:
        max_borrowable = await client.get_max_borrowable(base_asset)
    finally:
        await client.transfer(quote_asset, args.collateral, margin=False)
    return max_borrowable


async def max_manual(informant: Informant, chandler: Chandler, symbol: str) -> Decimal:
    candle = await chandler.get_last_candle('binance', symbol, time.MIN_MS)
    margin_multiplier = informant.get_margin_multiplier('binance')
    _, filters = informant.get_fees_filters('binance', symbol)

    collateral_size = filters.size.round_down(args.collateral / candle.close)
    return collateral_size * (margin_multiplier - 1)


asyncio.run(main())