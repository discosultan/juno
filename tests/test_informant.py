from decimal import Decimal
from typing import Optional

import pytest
from pytest_mock import MockerFixture

from juno import AssetInfo, ExchangeInfo, Fees, Filters, Ticker
from juno.components import Informant
from juno.filters import Price, Size
from juno.storages import Storage
from tests.mocks import mock_exchange

from . import fakes


@pytest.mark.parametrize("exchange_key", ["__all__", "eth-btc"])
async def test_get_fees_filters(
    mocker: MockerFixture, storage: Storage, exchange_key: str
) -> None:
    fees = Fees(maker=Decimal("0.001"), taker=Decimal("0.002"))
    filters = Filters(
        price=Price(min=Decimal("1.0"), max=Decimal("1.0"), step=Decimal("1.0")),
        size=Size(min=Decimal("1.0"), max=Decimal("1.0"), step=Decimal("1.0")),
    )
    exchange = mock_exchange(
        mocker,
        exchange_info=ExchangeInfo(fees={exchange_key: fees}, filters={exchange_key: filters}),
    )

    async with Informant(storage=storage, exchanges=[exchange]) as informant:
        out_fees, out_filters = informant.get_fees_filters(exchange.name, "eth-btc")

        assert out_fees == fees
        assert out_filters == filters


@pytest.mark.parametrize(
    "symbols,patterns,expected_output",
    [
        (["eth-btc", "ltc-btc"], None, ["eth-btc", "ltc-btc"]),
        (["eth-btc", "ltc-btc", "ltc-eth"], ["*-btc"], ["eth-btc", "ltc-btc"]),
        (["eth-btc", "ltc-btc", "ltc-eth"], ["eth-btc", "ltc-btc"], ["eth-btc", "ltc-btc"]),
        (["eth-btc", "ltc-eur"], ["*-*"], ["eth-btc", "ltc-eur"]),
    ],
)
async def test_list_symbols(
    mocker: MockerFixture,
    storage: Storage,
    symbols: list[str],
    patterns: Optional[list[str]],
    expected_output: list[str],
) -> None:
    exchange = mock_exchange(
        mocker, exchange_info=ExchangeInfo(filters={s: Filters() for s in symbols})
    )

    async with Informant(storage=storage, exchanges=[exchange]) as informant:
        output = informant.list_symbols(exchange.name, patterns)

    assert len(output) == len(expected_output)
    assert set(output) == set(expected_output)


async def test_resource_caching_to_storage(mocker: MockerFixture, storage) -> None:
    time = fakes.Time(time=0)
    exchange = mock_exchange(mocker, can_list_all_tickers=False)

    async with Informant(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time,
        cache_time=1,
    ):
        pass

    assert exchange.get_exchange_info.call_count == 1
    assert len(storage.get_calls) == 1
    assert len(storage.set_calls) == 1

    async with Informant(
        storage=storage,
        exchanges=[exchange],
        get_time_ms=time.get_time,
        cache_time=1,
    ):
        pass

    assert exchange.get_exchange_info.call_count == 1
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

    assert exchange.get_exchange_info.call_count == 2
    assert len(storage.get_calls) == 3
    assert len(storage.set_calls) == 2


async def test_map_tickers_exclude_symbol_patterns(
    mocker: MockerFixture, storage: Storage
) -> None:
    ticker = Ticker(
        volume=Decimal("1.0"),
        quote_volume=Decimal("1.0"),
        price=Decimal("1.0"),
    )
    tickers = {
        "btc": ticker,
        "eth": ticker,
        "ltc": ticker,
    }

    exchange = mock_exchange(mocker, tickers=tickers)

    async with Informant(storage=storage, exchanges=[exchange]) as informant:
        assert informant.map_tickers(exchange.name, exclude_symbol_patterns=None) == tickers
        assert informant.map_tickers(exchange.name, exclude_symbol_patterns=[]) == tickers
        assert informant.map_tickers(exchange.name, exclude_symbol_patterns=["btc"]) == {
            "eth": ticker,
            "ltc": ticker,
        }
        assert informant.map_tickers(exchange.name, exclude_symbol_patterns=["btc", "eth"]) == {
            "ltc": ticker,
        }


async def test_get_asset_info(mocker: MockerFixture, storage: Storage) -> None:
    exchange = mock_exchange(
        mocker,
        exchange_info=ExchangeInfo(
            assets={
                "__all__": AssetInfo(precision=1),
                "btc": AssetInfo(precision=2),
            }
        ),
    )

    async with Informant(storage=storage, exchanges=[exchange]) as informant:
        assert informant.get_asset_info(exchange.name, "btc").precision == 2
        assert informant.get_asset_info(exchange.name, "eth").precision == 1
