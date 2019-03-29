import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
import logging
import os

import plotly.offline as py
import plotly.graph_objs as go

from juno.components import Informant
from juno.exchanges import Binance
from juno.storages import SQLite
from juno.time import datetime_timestamp_ms, datetime_utcfromtimestamp_ms, HOUR_MS
from juno.utils import list_async


async def main():
    async with new_informat() as informant:
        blah = await list_async(informant.stream_candles(
            'binance',
            'eth-btc',
            HOUR_MS,
            datetime_timestamp_ms(datetime(2017, 1, 1)),
            datetime_timestamp_ms(datetime(2018, 1, 1))))

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
                       os.environ['JUNO__BINANCE__SECRET_KEY']) as client:
        async with SQLite() as storage:
            services = {
                'sqlite': storage,
                'binance': client
            }
            config = {
                'storage': 'sqlite'
            }
            async with Informant(services, config) as informant:
                yield informant

logging.basicConfig(level='INFO')
asyncio.run(main())
