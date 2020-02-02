from decimal import Decimal

import pytest

from juno import Balance, Candle, DepthSnapshot, ExchangeInfo, Fees
from juno.components import Historian, Informant, Orderbook, Wallet
from juno.filters import Filters, Price, Size

from . import fakes


@pytest.mark.parametrize('earliest_exchange_start,time', [
    (10, 20),  # Simple happy flow.
    (0, 16),  # `final_end` and start not being over-adjusted.
])
async def test_get_first_candle_time(storage, earliest_exchange_start, time):
    candles = [
        Candle(time=12),
        Candle(time=14),
        Candle(time=16),
        Candle(time=18),
    ]
    historian = Historian(
        chandler=fakes.Chandler(candles={('exchange', 'eth-btc', 2): candles}),
        storage=storage,
        get_time_ms=fakes.Time(time).get_time,
        earliest_exchange_start=earliest_exchange_start)

    first_candle_time = await historian.find_first_candle_time('exchange', 'eth-btc', 2)

    assert first_candle_time == 12


@pytest.mark.parametrize('earliest_exchange_start,time', [
    (1, 2),  # No candles
    (0, 1),  # Single last candle.
])
async def test_get_first_candle_time_not_found(storage, earliest_exchange_start, time):
    historian = Historian(
        chandler=fakes.Chandler(candles={('exchange', 'eth-btc', 1): [Candle(time=0)]}),
        storage=storage,
        get_time_ms=fakes.Time(time).get_time,
        earliest_exchange_start=earliest_exchange_start)

    with pytest.raises(ValueError):
        await historian.find_first_candle_time('exchange', 'eth-btc', 1)


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


@pytest.mark.parametrize('symbols,patterns,expected_output', [
    (['eth-btc', 'ltc-btc'], None, ['eth-btc', 'ltc-btc']),
    (['eth-btc', 'ltc-btc', 'ltc-eth'], ['*-btc'], ['eth-btc', 'ltc-btc']),
    (['eth-btc', 'ltc-btc', 'ltc-eth'], ['eth-btc', 'ltc-btc'], ['eth-btc', 'ltc-btc']),
])
async def test_list_symbols(storage, symbols, patterns, expected_output):
    exchange = fakes.Exchange(
        exchange_info=ExchangeInfo(filters={s: Filters() for s in symbols})
    )

    async with Informant(storage=storage, exchanges=[exchange]) as informant:
        output = informant.list_symbols('exchange', patterns)

    assert len(output) == len(expected_output)
    assert set(output) == set(expected_output)


@pytest.mark.parametrize('intervals,patterns,expected_output', [
    ([1, 2], None, [1, 2]),
    ([1, 2, 3], [1, 2], [1, 2]),
])
async def test_list_candle_intervals(storage, intervals, patterns, expected_output):
    exchange = fakes.Exchange(
        exchange_info=ExchangeInfo(candle_intervals=intervals)
    )

    async with Informant(storage=storage, exchanges=[exchange]) as informant:
        output = informant.list_candle_intervals('exchange', patterns)

    assert len(output) == len(expected_output)
    assert set(output) == set(expected_output)


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
    exchange.can_stream_depth_snapshot = False

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
