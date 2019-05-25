from contextlib import asynccontextmanager
from decimal import Decimal

import pytest

from juno import Balance, DepthUpdate, DepthUpdateType, Fees
from juno.asyncio import list_async
from juno.components import Informant, Orderbook, Wallet
from juno.filters import Filters, Price, Size
from juno.storages import Memory

from . import fakes
from .utils import new_candle


async def test_stream_candles(loop):
    candles = [
        new_candle(time=0),
        new_candle(time=1),
        # Deliberately skipped candle.
        new_candle(time=3)
    ]
    async with init_informant(fakes.Exchange(candles=candles)) as informant:
        # -> 0
        # -> 1
        # -> 2 missing
        out_candles = await list_async(informant.stream_candles('exchange', 'eth-btc', 1, 0, 3))
        assert out_candles == candles[:2]

        # -> 2 missing
        out_candles = await list_async(informant.stream_candles('exchange', 'eth-btc', 1, 2, 3))
        assert out_candles == []

        # -> 2 missing
        # -> 3
        out_candles = await list_async(informant.stream_candles('exchange', 'eth-btc', 1, 3, 4))
        assert out_candles == candles[-1:]


@pytest.mark.parametrize('exchange_fees_key', ['__all__', 'eth-btc'])
async def test_get_fees(loop, exchange_fees_key):
    fees = Fees(maker=Decimal('0.001'), taker=Decimal('0.002'))
    async with init_informant(fakes.Exchange(fees={exchange_fees_key: fees})) as informant:
        out_fees = informant.get_fees('exchange', 'eth-btc')
        assert out_fees == fees


@pytest.mark.parametrize('exchange_filters_key', ['__all__', 'eth-btc'])
async def test_get_filters(loop, exchange_filters_key):
    filters = Filters(
        price=Price(min=Decimal(1), max=Decimal(1), step=Decimal(1)),
        size=Size(min=Decimal(1), max=Decimal(1), step=Decimal(1)))
    async with init_informant(fakes.Exchange(filters={exchange_filters_key: filters})
                              ) as informant:
        out_filters = informant.get_filters('exchange', 'eth-btc')
        assert out_filters == filters


async def test_list_asks_bids(loop):
    depths = [
        DepthUpdate(
            type=DepthUpdateType.SNAPSHOT,
            asks=[(Decimal(1), Decimal(1)), (Decimal(3), Decimal(1)), (Decimal(2), Decimal(1))],
            bids=[(Decimal(1), Decimal(1)), (Decimal(3), Decimal(1)), (Decimal(2), Decimal(1))])
    ]
    async with init_orderbook(fakes.Exchange(depths=depths)) as orderbook:
        asks = orderbook.list_asks(exchange='exchange', symbol='eth-btc')
        bids = orderbook.list_bids(exchange='exchange', symbol='eth-btc')

    assert asks == [(Decimal(1), Decimal(1)), (Decimal(2), Decimal(1)), (Decimal(3), Decimal(1))]
    assert bids == [(Decimal(3), Decimal(1)), (Decimal(2), Decimal(1)), (Decimal(1), Decimal(1))]


async def test_get_balance(loop):
    balance = Balance(available=Decimal(1), hold=Decimal(0))
    async with init_wallet(fakes.Exchange(balances=[{'btc': balance}])) as wallet:
        out_balance = wallet.get_balance('exchange', 'btc')
        assert out_balance == balance


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
