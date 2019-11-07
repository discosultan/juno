import asyncio
from decimal import Decimal

import pytest

from juno import Balance, Candle, DepthSnapshot, Fees, SymbolsInfo, Trade
from juno.asyncio import list_async
from juno.components import Chandler, Informant, Orderbook, Trades, Wallet
from juno.filters import Filters, Price, Size
from juno.storages import Memory

from . import fakes
from .utils import new_candle


@pytest.fixture
async def memory(loop):
    async with Memory() as memory:
        yield memory


@pytest.mark.parametrize(
    'start,end,closed,efrom,eto,espans', [
        [0, 3, True, 0, 2, [(0, 2)]],  # Skips skipped candle at the end.
        [2, 3, True, 0, 0, []],  # Empty if only skipped candle.
        [3, 5, True, 2, 5, [(3, 5)]],  # Filters out closed candle.
        [0, 5, False, 0, 5, [(0, 2), (2, 5)]],  # Includes closed candle.
        [0, 6, True, 0, 6, [(0, 2), (2, 5), (5, 6)]],  # Includes future candle.
        [5, 6, False, 5, 6, [(5, 6)]],  # Only future candle.
    ]
)
async def test_stream_candles(memory, start, end, closed, efrom, eto, espans):
    EXCHANGE = 'exchange'
    SYMBOL = 'eth-btc'
    INTERVAL = 1
    CURRENT = 5
    STORAGE_BATCH_SIZE = 2
    historical_candles = [
        new_candle(time=0),
        new_candle(time=1),
        # Deliberately skipped candle.
        new_candle(time=3),
        new_candle(time=4, closed=False),
        new_candle(time=4),
    ]
    future_candles = [
        new_candle(time=5),
    ]
    expected_candles = (historical_candles + future_candles)[efrom:eto]
    if closed:
        expected_candles = [c for c in expected_candles if c.closed]
    time = fakes.Time(CURRENT)
    exchange = fakes.Exchange(
        historical_candles=historical_candles,
        future_candles=future_candles,
    )
    trades = Trades(storage=memory, exchanges=[exchange])
    chandler = Chandler(
        trades=trades, storage=memory, exchanges=[exchange], get_time=time.get_time,
        storage_batch_size=STORAGE_BATCH_SIZE
    )

    output_candles = await list_async(
        chandler.stream_candles(EXCHANGE, SYMBOL, INTERVAL, start, end, closed)
    )
    db_key = (EXCHANGE, SYMBOL, INTERVAL)
    stored_spans, stored_candles = await asyncio.gather(
        list_async(memory.stream_time_series_spans(db_key, Candle, start, end)),
        list_async(memory.stream_time_series(db_key, Candle, start, end)),
    )

    assert output_candles == expected_candles
    assert stored_candles == [c for c in output_candles if c.closed]
    assert stored_spans == espans


@pytest.mark.parametrize(
    'start,end,efrom,eto,espans', [
        [1, 5, 1, 3, [(1, 5)]],  # Middle trades.
        [2, 4, 0, 0, []],  # Empty if no trades.
        [0, 7, 0, 5, [(0, 7)]],  # Includes future trade.
        [0, 4, 0, 2, [(0, 4)]],  # Middle trades with cap at the end.
    ]
)
async def test_stream_trades(memory, start, end, efrom, eto, espans):
    EXCHANGE = 'exchange'
    SYMBOL = 'eth-btc'
    CURRENT = 6
    # STORAGE_BATCH_SIZE = 2  # TODO <<<---------
    historical_trades = [
        Trade(time=0, price=Decimal(1), size=Decimal(1)),
        Trade(time=1, price=Decimal(2), size=Decimal(2)),
        Trade(time=4, price=Decimal(3), size=Decimal(3)),
        Trade(time=5, price=Decimal(4), size=Decimal(4)),
    ]
    future_trades = [
        Trade(time=6, price=Decimal(1), size=Decimal(1)),
    ]
    expected_trades = (historical_trades + future_trades)[efrom:eto]
    time = fakes.Time(CURRENT)
    exchange = fakes.Exchange(
        historical_trades=historical_trades,
        future_trades=future_trades,
    )
    trades = Trades(
        storage=memory, exchanges=[exchange], get_time=time.get_time
    )

    output_trades = await list_async(trades.stream_trades(EXCHANGE, SYMBOL, start, end))
    db_key = (EXCHANGE, SYMBOL)
    stored_spans, stored_trades = await asyncio.gather(
        list_async(memory.stream_time_series_spans(db_key, Trade, start, end)),
        list_async(memory.stream_time_series(db_key, Trade, start, end)),
    )

    assert output_trades == expected_trades
    assert stored_trades == output_trades
    assert stored_spans == espans


@pytest.mark.parametrize('exchange_key', ['__all__', 'eth-btc'])
async def test_get_fees_filters(memory, exchange_key):
    fees = Fees(maker=Decimal('0.001'), taker=Decimal('0.002'))
    filters = Filters(
        price=Price(min=Decimal(1), max=Decimal(1), step=Decimal(1)),
        size=Size(min=Decimal(1), max=Decimal(1), step=Decimal(1))
    )
    exchange = fakes.Exchange(
        symbol_info=SymbolsInfo(fees={exchange_key: fees}, filters={exchange_key: filters})
    )

    async with Informant(storage=memory, exchanges=[exchange]) as informant:
        out_fees, out_filters = informant.get_fees_filters('exchange', 'eth-btc')

        assert out_fees == fees
        assert out_filters == filters


async def test_list_symbols(memory):
    symbols = ['eth-btc', 'ltc-btc']
    exchange = fakes.Exchange(
        symbol_info=SymbolsInfo(fees=Fees.none(), filters={s: Filters.none() for s in symbols})
    )

    async with Informant(storage=memory, exchanges=[exchange]) as informant:
        out_symbols = informant.list_symbols('exchange')

    assert out_symbols == symbols


async def test_list_asks_bids(memory):
    snapshot = DepthSnapshot(
        asks=[(Decimal(1), Decimal(1)), (Decimal(3), Decimal(1)), (Decimal(2), Decimal(1))],
        bids=[(Decimal(1), Decimal(1)), (Decimal(3), Decimal(1)), (Decimal(2), Decimal(1))]
    )
    exchange = fakes.Exchange(depth=snapshot)

    async with Orderbook(exchanges=[exchange], config={'symbol': 'eth-btc'}) as orderbook:
        asks = orderbook.list_asks(exchange='exchange', symbol='eth-btc')
        bids = orderbook.list_bids(exchange='exchange', symbol='eth-btc')

    assert asks == [(Decimal(1), Decimal(1)), (Decimal(2), Decimal(1)), (Decimal(3), Decimal(1))]
    assert bids == [(Decimal(3), Decimal(1)), (Decimal(2), Decimal(1)), (Decimal(1), Decimal(1))]


async def test_get_balance():
    balance = Balance(available=Decimal(1), hold=Decimal(0))
    exchange = fakes.Exchange(balances={'btc': balance})

    async with Wallet(exchanges=[exchange]) as wallet:
        out_balance = wallet.get_balance('exchange', 'btc')

    assert out_balance == balance
