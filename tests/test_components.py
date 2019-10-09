from contextlib import asynccontextmanager
from decimal import Decimal

import pytest

from juno import Balance, DepthSnapshot, Fees, SymbolsInfo
from juno.asyncio import list_async
from juno.components import Chandler, Informant, Orderbook, Wallet
from juno.filters import Filters, Price, Size
from juno.storages import Memory

from . import fakes
from .utils import new_candle


@pytest.mark.parametrize(
    'start,end,closed,expected_from,expected_to', [
        [0, 3, True, 0, 2],
        [2, 3, True, 0, 0],
        [3, 5, True, 2, 3],
        [0, 5, False, 0, 5],
    ]
)
async def test_stream_candles(start, end, closed, expected_from, expected_to):
    candles = [
        new_candle(time=0),
        new_candle(time=1),
        # Deliberately skipped candle.
        new_candle(time=3),
        new_candle(time=4, closed=False),
    ]
    async with init_chandler(fakes.Exchange(historical_candles=candles)) as chandler:
        expected_candles = candles[expected_from:expected_to]
        candles = await list_async(
            chandler.stream_candles('exchange', 'eth-btc', 1, start, end, closed)
        )
        assert candles == expected_candles


@pytest.mark.parametrize('exchange_key', ['__all__', 'eth-btc'])
async def test_get_fees_filters(exchange_key):
    fees = Fees(maker=Decimal('0.001'), taker=Decimal('0.002'))
    filters = Filters(
        price=Price(min=Decimal(1), max=Decimal(1), step=Decimal(1)),
        size=Size(min=Decimal(1), max=Decimal(1), step=Decimal(1))
    )
    async with init_informant(fakes.Exchange(symbol_info=SymbolsInfo(
        fees={exchange_key: fees},
        filters={exchange_key: filters}
    ))) as informant:
        out_fees, out_filters = informant.get_fees_filters('exchange', 'eth-btc')
        assert out_fees == fees
        assert out_filters == filters


async def test_list_symbols():
    symbols = ['eth-btc', 'ltc-btc']
    async with init_informant(
        fakes.Exchange(symbol_info=SymbolsInfo(
            fees=Fees.none(),
            filters={s: Filters.none() for s in symbols}
        ))
    ) as informant:
        out_symbols = informant.list_symbols('exchange')
        assert out_symbols == symbols


async def test_list_asks_bids():
    snapshot = DepthSnapshot(
        asks=[(Decimal(1), Decimal(1)), (Decimal(3), Decimal(1)), (Decimal(2), Decimal(1))],
        bids=[(Decimal(1), Decimal(1)), (Decimal(3), Decimal(1)), (Decimal(2), Decimal(1))]
    )
    async with init_orderbook(fakes.Exchange(depth_snapshot=snapshot)) as orderbook:
        asks = orderbook.list_asks(exchange='exchange', symbol='eth-btc')
        bids = orderbook.list_bids(exchange='exchange', symbol='eth-btc')

    assert asks == [(Decimal(1), Decimal(1)), (Decimal(2), Decimal(1)), (Decimal(3), Decimal(1))]
    assert bids == [(Decimal(3), Decimal(1)), (Decimal(2), Decimal(1)), (Decimal(1), Decimal(1))]


async def test_get_balance():
    balance = Balance(available=Decimal(1), hold=Decimal(0))
    async with init_wallet(fakes.Exchange(balances=[{'btc': balance}])) as wallet:
        out_balance = wallet.get_balance('exchange', 'btc')
        assert out_balance == balance


@asynccontextmanager
async def init_chandler(exchange):
    async with Memory() as memory:
        yield Chandler(storage=memory, exchanges=[exchange])


@asynccontextmanager
async def init_informant(exchange):
    async with Memory() as memory:
        async with Informant(storage=memory, exchanges=[exchange]) as component:
            yield component


@asynccontextmanager
async def init_orderbook(exchange):
    async with Orderbook(exchanges=[exchange], config={'symbol': 'eth-btc'}) as component:
        yield component


@asynccontextmanager
async def init_wallet(exchange):
    async with Wallet(exchanges=[exchange]) as component:
        yield component
