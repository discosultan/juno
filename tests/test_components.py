from decimal import Decimal

import pytest

from juno import Balance, Candle, DepthSnapshot
from juno.components import Historian, Orderbook, Wallet

from . import fakes


@pytest.mark.parametrize('earliest_exchange_start,time', [
    (10, 20),  # Simple happy flow.
    (0, 16),  # `final_end` and start not being over-adjusted.
])
async def test_find_first_candle(storage, earliest_exchange_start, time) -> None:
    candles = [
        Candle(time=12),
        Candle(time=14),
        Candle(time=16),
        Candle(time=18),
    ]
    exchange = fakes.Exchange()
    exchange.can_stream_historical_earliest_candle = False
    historian = Historian(
        chandler=fakes.Chandler(candles={('exchange', 'eth-btc', 2): candles}),  # type: ignore
        storage=storage,
        exchanges=[exchange],
        get_time_ms=fakes.Time(time).get_time,
        earliest_exchange_start=earliest_exchange_start
    )

    first_candle = await historian.find_first_candle('exchange', 'eth-btc', 2)

    assert first_candle.time == 12


@pytest.mark.parametrize('earliest_exchange_start,time', [
    (1, 2),  # No candles
    (0, 1),  # Single last candle.
])
async def test_find_first_candle_not_found(storage, earliest_exchange_start, time) -> None:
    exchange = fakes.Exchange()
    exchange.can_stream_historical_earliest_candle = False
    historian = Historian(
        chandler=fakes.Chandler(
            candles={('exchange', 'eth-btc', 1): [Candle(time=0)]}
        ),  # type: ignore
        storage=storage,
        exchanges=[exchange],
        get_time_ms=fakes.Time(time).get_time,
        earliest_exchange_start=earliest_exchange_start
    )

    with pytest.raises(ValueError):
        await historian.find_first_candle('exchange', 'eth-btc', 1)


async def test_list_asks_bids(storage) -> None:
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


async def test_get_balance() -> None:
    balance = Balance(available=Decimal('1.0'), hold=Decimal('0.0'))
    exchange = fakes.Exchange(balances={'btc': balance})

    async with Wallet(exchanges=[exchange]) as wallet:
        out_balance = wallet.get_balance('exchange', 'btc')

    assert out_balance == balance
