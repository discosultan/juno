from decimal import Decimal

import pytest

from juno import Candle
from juno.components import Prices

from . import fakes


@pytest.mark.parametrize('symbols,chandler_symbols,expected_output', [
    # Basic.
    (
        ['eth-btc'],
        ['eth-btc', 'btc-usdt'],
        {
            'eth': [Decimal('1.0'), Decimal('4.0'), Decimal('9.0')],
            'btc': [Decimal('1.0'), Decimal('2.0'), Decimal('3.0')],
        },
    ),
    # Fiat as quote.
    (
        ['btc-usdt'],
        ['btc-usdt'],
        {
            'btc': [Decimal('1.0'), Decimal('2.0'), Decimal('3.0')],
            'usdt': [Decimal('1.0'), Decimal('1.0'), Decimal('1.0')],
        },
    ),
    # Combined.
    (
        ['eth-btc', 'btc-usdt'],
        ['eth-btc', 'btc-usdt'],
        {
            'eth': [Decimal('1.0'), Decimal('4.0'), Decimal('9.0')],
            'btc': [Decimal('1.0'), Decimal('2.0'), Decimal('3.0')],
            'usdt': [Decimal('1.0'), Decimal('1.0'), Decimal('1.0')],
        },
    ),
])
async def test_map_asset_prices(symbols, chandler_symbols, expected_output) -> None:
    candles = [
        Candle(time=0, close=Decimal('1.0')),
        Candle(time=1, close=Decimal('2.0')),
        Candle(time=2, close=Decimal('3.0')),
    ]
    prices = Prices(
        chandler=fakes.Chandler(candles={('exchange', s, 1): candles for s in chandler_symbols}),
    )
    output = await prices.map_asset_prices(
        exchange='exchange',
        symbols=symbols,
        interval=1,
        fiat_asset='usdt',
        start=0,
        end=3,
    )
    assert output == expected_output


@pytest.mark.parametrize('symbols,expected_output', [
    (
        ['eth-btc'],
        {
            'eth': [Decimal('2.0'), Decimal('8.0'), Decimal('18.0')],
            'btc': [Decimal('2.0'), Decimal('4.0'), Decimal('6.0')],
        },
    ),
    (
        ['eth-btc', 'btc-usdt'],
        {
            'eth': [Decimal('2.0'), Decimal('8.0'), Decimal('18.0')],
            'btc': [Decimal('2.0'), Decimal('4.0'), Decimal('6.0')],
            'usdt': [Decimal('1.0'), Decimal('1.0'), Decimal('1.0')],
        },
    ),
    (
        ['btc-usdt'],
        {
            'btc': [Decimal('2.0'), Decimal('4.0'), Decimal('6.0')],
            'usdt': [Decimal('1.0'), Decimal('1.0'), Decimal('1.0')],
        },
    ),
])
async def test_map_asset_prices_with_different_fiat_exchange(symbols, expected_output) -> None:
    exchange1_candles = [
        Candle(time=0, close=Decimal('1.0')),
        Candle(time=1, close=Decimal('2.0')),
        Candle(time=2, close=Decimal('3.0')),
    ]
    exchange2_candles = [
        Candle(time=0, close=Decimal('2.0')),
        Candle(time=1, close=Decimal('4.0')),
        Candle(time=2, close=Decimal('6.0')),
    ]
    prices = Prices(
        chandler=fakes.Chandler(candles={
            ('exchange1', 'eth-btc', 1): exchange1_candles,
            ('exchange2', 'btc-usdt', 1): exchange2_candles,
        }),
    )
    output = await prices.map_asset_prices(
        exchange='exchange1',
        symbols=symbols,
        interval=1,
        fiat_exchange='exchange2',
        fiat_asset='usdt',
        start=0,
        end=3,
    )
    assert output == expected_output
