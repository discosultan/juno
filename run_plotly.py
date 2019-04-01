import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import os

import plotly.offline as py
import plotly.graph_objs as go

from juno.components import Informant
from juno.exchanges import Binance, Coinbase
from juno.storages import Memory, SQLite
from juno.time import datetime_timestamp_ms, datetime_utcfromtimestamp_ms, HOUR_MS, DAY_MS
from juno.utils import list_async


async def main():
    async with new_informat() as informant:
        blah = await list_async(informant.stream_candles(
            'binance',
            'eth-btc',
            HOUR_MS,
            datetime_timestamp_ms(datetime(2017, 1, 20, tzinfo=timezone.utc)),
            datetime_timestamp_ms(datetime(2017, 9, 10, tzinfo=timezone.utc))))

    candles = [c for c, p in blah]
    trace = go.Ohlc(
        x=[datetime_utcfromtimestamp_ms(c.time) for c in candles],
        open=[c.open for c in candles],
        high=[c.high for c in candles],
        low=[c.low for c in candles],
        close=[c.close for c in candles])
    data = [trace]
    py.plot(data)


@asynccontextmanager
async def new_informat():
    async with Binance(os.environ['JUNO__BINANCE__API_KEY'],
                       os.environ['JUNO__BINANCE__SECRET_KEY']) as binance:
        async with Coinbase(os.environ['JUNO__COINBASE__API_KEY'],
                            os.environ['JUNO__COINBASE__SECRET_KEY'],
                            os.environ['JUNO__COINBASE__PASSPHRASE']) as coinbase:
            async with SQLite() as sqlite:
                async with Memory() as memory:
                    services = {
                        'memory': memory,
                        'sqlite': sqlite,
                        'binance': binance,
                        'coinbase': coinbase
                    }
                    config = {
                        'storage': 'sqlite'
                    }
                    async with Informant(services, config) as informant:
                        yield informant

logging.basicConfig(level='INFO')
asyncio.run(main())
