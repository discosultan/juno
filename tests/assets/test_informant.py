from decimal import Decimal

import pytest

from juno.assets import BorrowInfo, ExchangeInfo, Fees, Filters, Informant, Ticker
from juno.assets.filters import Price, Size
from tests import fakes

from .mock import mock_exchange_assets

EXCHANGE = 'magicmock'
SYMBOL = 'eth-btc'


@pytest.mark.parametrize('exchange_key', ['__all__', 'eth-btc'])
async def test_get_fees_filters(storage, exchange_key) -> None:
    fees = Fees(maker=Decimal('0.001'), taker=Decimal('0.002'))
    filters = Filters(
        price=Price(min=Decimal('1.0'), max=Decimal('1.0'), step=Decimal('1.0')),
        size=Size(min=Decimal('1.0'), max=Decimal('1.0'), step=Decimal('1.0'))
    )
    exchange = mock_exchange_assets(
        exchange_info=ExchangeInfo(fees={exchange_key: fees}, filters={exchange_key: filters})
    )

    async with Informant(storage=storage, exchanges=[exchange]) as informant:
        out_fees, out_filters = informant.get_fees_filters(EXCHANGE, SYMBOL)

        assert out_fees == fees
        assert out_filters == filters


@pytest.mark.parametrize('patterns,borrow,expected_output', [
    (None, False, ['eth', 'btc', 'ltc']),
    (None, True, ['eth', 'btc']),
    (['*'], False, ['eth', 'btc', 'ltc']),
    (['btc'], False, ['btc']),
])
async def test_list_assets(storage, patterns, borrow, expected_output) -> None:
    exchange = mock_exchange_assets(
        exchange_info=ExchangeInfo(
            borrow_info={
                '__all__': {
                    'btc': BorrowInfo(),
                    'eth': BorrowInfo(),
                }
            },
            filters={
                'eth-btc': Filters(),
                'ltc-btc': Filters(),
            }
        )
    )

    async with Informant(storage=storage, exchanges=[exchange]) as informant:
        assert informant.list_assets(
            EXCHANGE, patterns=patterns, borrow=borrow
        ) == expected_output


@pytest.mark.parametrize('symbols,patterns,expected_output', [
    (['eth-btc', 'ltc-btc'], None, ['eth-btc', 'ltc-btc']),
    (['eth-btc', 'ltc-btc', 'ltc-eth'], ['*-btc'], ['eth-btc', 'ltc-btc']),
    (['eth-btc', 'ltc-btc', 'ltc-eth'], ['eth-btc', 'ltc-btc'], ['eth-btc', 'ltc-btc']),
    (['eth-btc', 'ltc-eur'], ['*-*'], ['eth-btc', 'ltc-eur']),
])
async def test_list_symbols(storage, symbols, patterns, expected_output) -> None:
    exchange = mock_exchange_assets(
        exchange_info=ExchangeInfo(filters={s: Filters() for s in symbols})
    )

    async with Informant(storage=storage, exchanges=[exchange]) as informant:
        output = informant.list_symbols(EXCHANGE, patterns)

    assert len(output) == len(expected_output)
    assert set(output) == set(expected_output)


async def test_resource_caching_to_storage(storage) -> None:
    time = fakes.Time(time=0)
    exchange = mock_exchange_assets(can_list_all_tickers=False)

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


async def test_map_tickers_exclude_symbol_patterns(storage) -> None:
    ticker = Ticker(
        volume=Decimal('1.0'),
        quote_volume=Decimal('1.0'),
        price=Decimal('1.0'),
    )
    tickers = {
        'btc': ticker,
        'eth': ticker,
        'ltc': ticker,
    }

    exchange = mock_exchange_assets(tickers=tickers)

    async with Informant(storage=storage, exchanges=[exchange]) as informant:
        assert informant.map_tickers(EXCHANGE, exclude_symbol_patterns=None) == tickers
        assert informant.map_tickers(EXCHANGE, exclude_symbol_patterns=[]) == tickers
        assert informant.map_tickers(EXCHANGE, exclude_symbol_patterns=['btc']) == {
            'eth': ticker,
            'ltc': ticker,
        }
        assert informant.map_tickers(EXCHANGE, exclude_symbol_patterns=['btc', 'eth']) == {
            'ltc': ticker,
        }
