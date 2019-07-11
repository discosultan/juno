import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

import plotly.graph_objs as go
import plotly.offline as py
from juno.asyncio import list_async
from juno.components import Informant
from juno.exchanges import Binance, Coinbase
from juno.storages import Memory, SQLite
from juno.time import HOUR_MS, UTC, datetime_timestamp_ms, datetime_utcfromtimestamp_ms


async def main():
    async with new_informat() as informant:
        candles = await list_async(informant.stream_candles(
            'binance',
            'eth-btc',
            HOUR_MS,
            datetime_timestamp_ms(datetime(2017, 1, 1, tzinfo=UTC)),
            datetime_timestamp_ms(datetime(2018, 1, 1, tzinfo=UTC))))

        candles_map = {c.time: c for c, p in candles}

        positions = [
            (1500120000000, 1500181200000), (1500296400000, 1500512400000),
            (1500850800000, 1500980400000), (1501387200000, 1501513200000),
            (1501563600000, 1501812000000), (1501995600000, 1502427600000),
            (1502895600000, 1502971200000), (1503136800000, 1503460800000),
            (1503889200000, 1504317600000), (1504674000000, 1504893600000),
            (1505210400000, 1505318400000), (1505696400000, 1506384000000),
            (1507136400000, 1507482000000), (1507932000000, 1508047200000),
            (1508137200000, 1508209200000), (1508824800000, 1509001200000),
            (1509292800000, 1509328800000), (1509800400000, 1509840000000),
            (1509991200000, 1510120800000), (1510185600000, 1510596000000),
            (1510678800000, 1510754400000), (1511056800000, 1511672400000),
            (1512770400000, 1512936000000), (1513062000000, 1513314000000),
            (1513584000000, 1513962000000), (1514174400000, 1514296800000),
            (1514462400000, 1514761200000)]

    candles = [c for c, p in candles]
    trace1 = go.Ohlc(
        x=[datetime_utcfromtimestamp_ms(c.time) for c in candles],
        open=[c.open for c in candles],
        high=[c.high for c in candles],
        low=[c.low for c in candles],
        close=[c.close for c in candles])
    trace2 = {
        'x': [datetime_utcfromtimestamp_ms(a) for a, _ in positions],
        'y': [candles_map[a].close for a, _ in positions],
        'marker': {
            'color': 'green',
            'size': 12
        },
        'type': 'scatter',
        'mode': 'markers'
    }
    trace3 = {
        'x': [datetime_utcfromtimestamp_ms(b) for _, b in positions],
        'y': [candles_map[b].close for _, b in positions],
        'marker': {
            'color': 'red',
            'size': 12
        },
        'mode': 'markers',
        'type': 'scatter'
    }
    data = [trace1, trace2, trace3]
    py.plot(data)


@asynccontextmanager
async def new_informat():
    binance = Binance(os.environ['JUNO__BINANCE__API_KEY'],
                      os.environ['JUNO__BINANCE__SECRET_KEY'])
    coinbase = Coinbase(os.environ['JUNO__COINBASE__API_KEY'],
                        os.environ['JUNO__COINBASE__SECRET_KEY'],
                        os.environ['JUNO__COINBASE__PASSPHRASE'])
    sqlite = SQLite()
    memory = Memory()
    async with binance, coinbase, sqlite, memory:
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
