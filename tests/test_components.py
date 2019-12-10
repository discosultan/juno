import asyncio
from decimal import Decimal

import pytest

from juno import Balance, Candle, DepthSnapshot, Fees, ExchangeInfo, JunoException, Trade
from juno.asyncio import cancel, cancelable, list_async
from juno.components import Chandler, Informant, Orderbook, Trades, Wallet
from juno.filters import Filters, Price, Size

from . import fakes


@pytest.fixture
async def storage(loop):
    async with fakes.Storage() as storage:
        yield storage


@pytest.mark.parametrize(
    'start,end,closed,efrom,eto,espans',
    [
        [0, 3, True, 0, 2, [(0, 2), (2, 3)]],  # Skips skipped candle at the end.
        [2, 3, True, 0, 0, [(2, 3)]],  # Empty if only skipped candle.
        [3, 5, True, 2, 5, [(3, 5)]],  # Filters out closed candle.
        [0, 5, False, 0, 5, [(0, 2), (2, 5)]],  # Includes closed candle.
        [0, 6, True, 0, 6, [(0, 2), (2, 5), (5, 6)]],  # Includes future candle.
        [5, 6, False, 5, 6, [(5, 6)]],  # Only future candle.
    ]
)
async def test_stream_candles(storage, start, end, closed, efrom, eto, espans):
    EXCHANGE = 'exchange'
    SYMBOL = 'eth-btc'
    INTERVAL = 1
    CURRENT = 5
    STORAGE_BATCH_SIZE = 2
    historical_candles = [
        Candle(time=0),
        Candle(time=1),
        # Deliberately skipped candle.
        Candle(time=3),
        Candle(time=4, closed=False),
        Candle(time=4),
    ]
    future_candles = [
        Candle(time=5),
    ]
    expected_candles = (historical_candles + future_candles)[efrom:eto]
    if closed:
        expected_candles = [c for c in expected_candles if c.closed]
    time = fakes.Time(CURRENT)
    exchange = fakes.Exchange(
        historical_candles=historical_candles,
        future_candles=future_candles,
    )
    trades = Trades(storage=storage, exchanges=[exchange])
    chandler = Chandler(
        trades=trades,
        storage=storage,
        exchanges=[exchange],
        get_time=time.get_time,
        storage_batch_size=STORAGE_BATCH_SIZE
    )

    output_candles = await list_async(
        chandler.stream_candles(EXCHANGE, SYMBOL, INTERVAL, start, end, closed)
    )
    storage_key = (EXCHANGE, SYMBOL, INTERVAL)
    stored_spans, stored_candles = await asyncio.gather(
        list_async(storage.stream_time_series_spans(storage_key, Candle, start, end)),
        list_async(storage.stream_time_series(storage_key, Candle, start, end)),
    )

    assert output_candles == expected_candles
    assert stored_candles == [c for c in output_candles if c.closed]
    assert stored_spans == espans


async def test_stream_future_candles_span_stored_until_stopped(storage):
    EXCHANGE = 'exchange'
    SYMBOL = 'eth-btc'
    INTERVAL = 1
    START = 0
    CANCEL_AT = 5
    END = 10
    candles = [Candle(time=1)]
    exchange = fakes.Exchange(future_candles=candles)
    trades = Trades(storage=storage, exchanges=[exchange])
    time = fakes.Time(START)
    chandler = Chandler(
        trades=trades,
        storage=storage,
        exchanges=[exchange],
        get_time=time.get_time,
    )

    task = asyncio.create_task(cancelable(
        list_async(chandler.stream_candles(EXCHANGE, SYMBOL, INTERVAL, START, END))
    ))
    await exchange.candle_queue.join()
    time.time = CANCEL_AT
    await cancel(task)

    storage_key = (EXCHANGE, SYMBOL, INTERVAL)
    stored_spans, stored_candles = await asyncio.gather(
        list_async(storage.stream_time_series_spans(storage_key, Candle, START, END)),
        list_async(storage.stream_time_series(storage_key, Candle, START, END)),
    )

    assert stored_candles == candles
    assert stored_spans == [(START, candles[-1].time + INTERVAL)]


async def test_stream_candles_construct_from_trades(storage):
    exchange = fakes.Exchange()
    exchange.can_stream_historical_candles = False
    exchange.can_stream_candles = False

    trades = fakes.Trades(trades=[
        Trade(time=0, price=Decimal('1.0'), size=Decimal('1.0')),
        Trade(time=1, price=Decimal('4.0'), size=Decimal('1.0')),
        Trade(time=3, price=Decimal('2.0'), size=Decimal('2.0')),
    ])
    chandler = Chandler(
        trades=trades,
        storage=storage,
        exchanges=[exchange],
    )

    output_candles = await list_async(chandler.stream_candles('exchange', 'eth-btc', 5, 0, 5))

    assert output_candles == [
        Candle(
            time=0,
            open=Decimal('1.0'),
            high=Decimal('4.0'),
            low=Decimal('1.0'),
            close=Decimal('2.0'),
            volume=Decimal('4.0'),
            closed=True
        )
    ]


async def test_stream_candles_cancel_does_not_store_twice(storage):
    candles = [Candle(time=1)]
    exchange = fakes.Exchange(historical_candles=candles)
    chandler = Chandler(
        trades=fakes.Trades(), storage=storage, exchanges=[exchange], storage_batch_size=1
    )

    stream_candles_task = asyncio.create_task(
        cancelable(list_async(chandler.stream_candles('exchange', 'eth-btc', 1, 0, 2)))
    )

    await storage.stored_time_series_and_span.wait()
    await cancel(stream_candles_task)

    stored_candles = await list_async(
        storage.stream_time_series(('exchange', 'eth-btc', 1), Candle, 0, 2)
    )
    assert stored_candles == candles


async def test_stream_candles_on_ws_disconnect(storage):
    time = fakes.Time(0)
    exchange = fakes.Exchange(future_candles=[
        Candle(time=0),
        Candle(time=1),
    ])
    chandler = Chandler(
        trades=fakes.Trades(), storage=storage, exchanges=[exchange], get_time=time.get_time
    )

    stream_candles_task = asyncio.create_task(
        list_async(chandler.stream_candles('exchange', 'eth-btc', 1, 0, 5))
    )
    await exchange.candle_queue.join()
    exchange.historical_candles = [
        Candle(time=0),
        Candle(time=1),
        Candle(time=2),
    ]
    exchange.future_candles = [
        Candle(time=3),
        Candle(time=4),
        Candle(time=5),
    ]
    time.time = 3
    stream_candles_task.get_coro().throw(JunoException())
    result = await stream_candles_task

    assert len(result) == 5
    for i, candle in enumerate(result):
        assert candle.time == i


async def test_stream_future_trades_span_stored_until_stopped(storage):
    EXCHANGE = 'exchange'
    SYMBOL = 'eth-btc'
    START = 0
    CANCEL_AT = 5
    END = 10
    trades = [Trade(time=1)]
    exchange = fakes.Exchange(future_trades=trades)
    time = fakes.Time(START)
    trades_component = Trades(storage=storage, exchanges=[exchange], get_time=time.get_time)

    task = asyncio.create_task(cancelable(
        list_async(trades_component.stream_trades(EXCHANGE, SYMBOL, START, END))
    ))
    await exchange.trade_queue.join()
    time.time = CANCEL_AT
    await cancel(task)

    storage_key = (EXCHANGE, SYMBOL)
    stored_spans, stored_trades = await asyncio.gather(
        list_async(storage.stream_time_series_spans(storage_key, Trade, START, END)),
        list_async(storage.stream_time_series(storage_key, Trade, START, END)),
    )

    assert stored_trades == trades
    assert stored_spans == [(START, trades[-1].time + 1)]


@pytest.mark.parametrize(
    'start,end,efrom,eto,espans',
    [
        [1, 5, 1, 3, [(1, 5)]],  # Middle trades.
        [2, 4, 0, 0, [(2, 4)]],  # Empty if no trades.
        [0, 7, 0, 5, [(0, 2), (2, 6), (6, 7)]],  # Includes future trade.
        [0, 4, 0, 2, [(0, 4)]],  # Middle trades with cap at the end.
    ]
)
async def test_stream_trades(storage, start, end, efrom, eto, espans):
    EXCHANGE = 'exchange'
    SYMBOL = 'eth-btc'
    CURRENT = 6
    STORAGE_BATCH_SIZE = 2
    historical_trades = [
        Trade(time=0, price=Decimal('1.0'), size=Decimal('1.0')),
        Trade(time=1, price=Decimal('2.0'), size=Decimal('2.0')),
        Trade(time=4, price=Decimal('3.0'), size=Decimal('3.0')),
        Trade(time=5, price=Decimal('4.0'), size=Decimal('4.0')),
    ]
    future_trades = [
        Trade(time=6, price=Decimal('1.0'), size=Decimal('1.0')),
        Trade(time=7, price=Decimal('1.0'), size=Decimal('1.0')),
    ]
    expected_trades = (historical_trades + future_trades)[efrom:eto]
    time = fakes.Time(CURRENT)
    exchange = fakes.Exchange(
        historical_trades=historical_trades,
        future_trades=future_trades,
    )
    trades = Trades(
        storage=storage,
        exchanges=[exchange],
        get_time=time.get_time,
        storage_batch_size=STORAGE_BATCH_SIZE
    )

    output_trades = await list_async(trades.stream_trades(EXCHANGE, SYMBOL, start, end))
    storage_key = (EXCHANGE, SYMBOL)
    stored_spans, stored_trades = await asyncio.gather(
        list_async(storage.stream_time_series_spans(storage_key, Trade, start, end)),
        list_async(storage.stream_time_series(storage_key, Trade, start, end)),
    )

    assert output_trades == expected_trades
    assert stored_trades == output_trades
    assert stored_spans == espans


@pytest.mark.parametrize('exchange_key', ['__all__', 'eth-btc'])
async def test_get_fees_filters(storage, exchange_key):
    fees = Fees(maker=Decimal('0.001'), taker=Decimal('0.002'))
    filters = Filters(
        price=Price(min=Decimal('1.0'), max=Decimal('1.0'), step=Decimal('1.0')),
        size=Size(min=Decimal('1.0'), max=Decimal('1.0'), step=Decimal('1.0'))
    )
    exchange = fakes.Exchange(
        exchange_info=ExchangeInfo(fees={exchange_key: fees}, filters={exchange_key: filters})
    )

    async with Informant(storage=storage, exchanges=[exchange]) as informant:
        out_fees, out_filters = informant.get_fees_filters('exchange', 'eth-btc')

        assert out_fees == fees
        assert out_filters == filters


async def test_list_symbols(storage):
    symbols = ['eth-btc', 'ltc-btc']
    exchange = fakes.Exchange(
        exchange_info=ExchangeInfo(fees=Fees(), filters={s: Filters() for s in symbols})
    )

    async with Informant(storage=storage, exchanges=[exchange]) as informant:
        out_symbols = informant.list_symbols('exchange')

    assert out_symbols == symbols


async def test_list_asks_bids(storage):
    snapshot = DepthSnapshot(
        asks=[
            (Decimal('1.0'), Decimal('1.0')),
            (Decimal('3.0'), Decimal('1.0')),
            (Decimal('2.0'), Decimal('1.0')),
        ],
        bids=[
            (Decimal('1.0'), Decimal('1.0')),
            (Decimal('3.0'), Decimal('1.0')),
            (Decimal('2.0'), Decimal('1.0')),
        ]
    )
    exchange = fakes.Exchange(depth=snapshot)

    async with Orderbook(exchanges=[exchange], config={'symbol': 'eth-btc'}) as orderbook:
        asks = orderbook.list_asks(exchange='exchange', symbol='eth-btc')
        bids = orderbook.list_bids(exchange='exchange', symbol='eth-btc')

    assert asks == [
        (Decimal('1.0'), Decimal('1.0')),
        (Decimal('2.0'), Decimal('1.0')),
        (Decimal('3.0'), Decimal('1.0')),
    ]
    assert bids == [
        (Decimal('3.0'), Decimal('1.0')),
        (Decimal('2.0'), Decimal('1.0')),
        (Decimal('1.0'), Decimal('1.0')),
    ]


async def test_get_balance():
    balance = Balance(available=Decimal('1.0'), hold=Decimal('0.0'))
    exchange = fakes.Exchange(balances={'btc': balance})

    async with Wallet(exchanges=[exchange]) as wallet:
        out_balance = wallet.get_balance('exchange', 'btc')

    assert out_balance == balance
