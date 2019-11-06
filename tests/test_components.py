from contextlib import asynccontextmanager
from decimal import Decimal

import pytest

from juno import Balance, DepthSnapshot, Fees, SymbolsInfo, Trade
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
    'start,end,closed,expected_from,expected_to', [
        [0, 3, True, 0, 2],
        [2, 3, True, 0, 0],
        [3, 5, True, 2, 3],
        [0, 5, False, 0, 5],
    ]
)
async def test_stream_candles(memory, start, end, closed, expected_from, expected_to):
    candles = [
        new_candle(time=0),
        new_candle(time=1),
        # Deliberately skipped candle.
        new_candle(time=3),
        new_candle(time=4, closed=False),
    ]
    expected_candles = candles[expected_from:expected_to]
    exchange = fakes.Exchange(historical_candles=candles)
    trades = Trades(storage=memory, exchanges=[exchange])
    chandler = Chandler(trades=trades, storage=memory, exchanges=[exchange])

    output_candles = await list_async(
        chandler.stream_candles('exchange', 'eth-btc', 1, start, end, closed)
    )

    assert output_candles == expected_candles


async def test_stream_trades(memory):
    trades = [
        Trade(time=0, price=Decimal(1), size=Decimal(1)),
        Trade(time=1, price=Decimal(2), size=Decimal(2)),
        Trade(time=3, price=Decimal(3), size=Decimal(3)),
        Trade(time=4, price=Decimal(4), size=Decimal(4)),
    ]
    expected_trades = trades[1:3]
    exchange = fakes.Exchange(historical_trades=trades)
    trades_component = Trades(storage=memory, exchanges=[exchange])

    output_trades = await list_async(trades_component.stream_trades('exchange', 'eth-btc', 1, 4))

    assert output_trades == expected_trades


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
