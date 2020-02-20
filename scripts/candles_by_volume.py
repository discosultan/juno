import asyncio
import logging
from decimal import Decimal

from juno.asyncio import list_async
from juno.components import Chandler, Informant, Trades
from juno.config import from_env, init_instance
from juno.exchanges import Binance
from juno.optimization.python import _trade
from juno.storages import SQLite
from juno.strategies import MA, MAMACX
from juno.time import strptimestamp
from juno.trading import MissedCandlePolicy
from juno.utils import tonamedtuple


async def main() -> None:
    start = strptimestamp('2020-01-01')
    end = strptimestamp('2020-01-02')
    interval = 1  # Arbitrary.
    binance = init_instance(Binance, from_env())
    sqlite = SQLite()
    informant = Informant(sqlite, [binance])
    trades = Trades(sqlite, [binance])
    chandler = Chandler(sqlite, [binance], informant=informant, trades=trades)
    async with binance, informant:
        candles = await list_async(
            chandler._stream_construct_candles_by_volume(
                'binance', 'eth-btc', Decimal('1000.0'), start, end
            )
        )
        fees, filters = informant.get_fees_filters('binance', 'eth-btc')
        strategy_args = (
            16,
            41,
            Decimal('-0.294'),
            Decimal('0.149'),
            8,
            MA.SMA,
            MA.SMA
        )
        summary = _trade(
            MAMACX,
            Decimal('1.0'),
            candles,
            fees,
            filters,
            'eth-btc',
            interval,
            MissedCandlePolicy.IGNORE,
            Decimal('0.1255'),
            *strategy_args
        )
        logging.info(tonamedtuple(summary))


asyncio.run(main())
