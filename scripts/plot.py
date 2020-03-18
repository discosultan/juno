import asyncio

import plotly.graph_objs as go
import plotly.offline as py
from juno.components import Chandler, Trades
from juno.config import from_env, init_instance
from juno.exchanges import Binance
from juno.storages import SQLite
from juno.time import HOUR_MS, datetime_utcfromtimestamp_ms, strptimestamp


async def main() -> None:
    sqlite = SQLite()
    binance = init_instance(Binance, from_env())
    trades = Trades(sqlite, [binance])
    chandler = Chandler(trades=trades, storage=sqlite, exchanges=[binance])
    async with binance:
        candles = await chandler.list_candles(
            exchange='binance',
            symbol='eth-btc',
            interval=HOUR_MS,
            start=strptimestamp('2017-01-01'),
            end=strptimestamp('2018-01-01'),
        )
        times = [datetime_utcfromtimestamp_ms(c.time) for c in candles]

        candles_map = {c.time: c for c in candles}

        positions = [(1500120000000, 1500181200000), (1500296400000, 1500512400000),
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

    trace1 = go.Ohlc(
        x=times,
        yaxis='y2',
        open=[c.open for c in candles],
        high=[c.high for c in candles],
        low=[c.low for c in candles],
        close=[c.close for c in candles]
    )
    trace2 = go.Scatter(
        x=[datetime_utcfromtimestamp_ms(a) for a, _ in positions],
        y=[candles_map[a].close for a, _ in positions],
        yaxis='y2',
        marker={
            'color': 'green',
            'size': 12,
        },
        mode='markers',
    )
    trace3 = go.Scatter(
        x=[datetime_utcfromtimestamp_ms(b) for _, b in positions],
        y=[candles_map[b].close for _, b in positions],
        yaxis='y2',
        marker={
            'color': 'red',
            'size': 12,
        },
        mode='markers',
    )
    trace4 = go.Bar(
        x=times,
        y=[c.volume for c in candles],
        yaxis='y',
        marker={
            'color': ['#006400' if c.close >= c.open else '#8b0000' for c in candles]
        }
    )
    data = [trace1, trace2, trace3, trace4]
    layout = {
        'yaxis': {
            'domain': [0, 0.2],
        },
        'yaxis2': {
            'domain': [0.2, 0.8],
        },
    }
    fig = go.Figure(data=data, layout=layout)
    py.plot(fig)


asyncio.run(main())
