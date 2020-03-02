from decimal import Decimal

import pytest

from juno import ExchangeInfo, Fees, Filters
from juno.components import Informant
from juno.filters import Price, Size

from . import fakes


@pytest.mark.parametrize('exchange_key', ['__all__', 'eth-btc'])
async def test_get_fees_filters(storage, exchange_key) -> None:
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
    (['eth-btc', 'ltc-eur'], ['*-*'], ['eth-btc', 'ltc-eur']),
])
async def test_list_symbols(storage, symbols, patterns, expected_output) -> None:
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
async def test_list_candle_intervals(storage, intervals, patterns, expected_output) -> None:
    exchange = fakes.Exchange(
        exchange_info=ExchangeInfo(candle_intervals=intervals)
    )

    async with Informant(storage=storage, exchanges=[exchange]) as informant:
        output = informant.list_candle_intervals('exchange', patterns)

    assert len(output) == len(expected_output)
    assert set(output) == set(expected_output)


async def test_resource_caching_to_storage(storage) -> None:
    time = fakes.Time(time=0)
    exchange = fakes.Exchange()
    exchange.can_list_all_tickers = False

    async with Informant(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time,
        cache_time=1,
    ):
        pass

    assert len(exchange.get_exchange_info_calls) == 1
    assert len(storage.get_calls) == 1
    assert len(storage.set_calls) == 1

    async with Informant(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time,
        cache_time=1,
    ):
        pass

    assert len(exchange.get_exchange_info_calls) == 1
    assert len(storage.get_calls) == 2
    assert len(storage.set_calls) == 1

    time.time = 2

    async with Informant(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time,
        cache_time=1,
    ):
        pass

    assert len(exchange.get_exchange_info_calls) == 2
    assert len(storage.get_calls) == 3
    assert len(storage.set_calls) == 2