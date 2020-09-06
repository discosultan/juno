from decimal import Decimal
from unittest.mock import AsyncMock

from juno import Balance
from juno.components import Wallet

from . import fakes


async def test_get_balance() -> None:
    balance = Balance(available=Decimal('1.0'), hold=Decimal('0.0'))
    exchange = fakes.Exchange(future_balances=[{'btc': balance}])
    exchange.can_margin_trade = False

    async with Wallet(exchanges=[exchange]) as wallet:
        out_balance = wallet.get_balance(
            exchange='exchange', account='spot', asset='btc'
        )

    assert out_balance == balance


async def test_all_significant_balances(mocker) -> None:
    exchange = mocker.patch('juno.exchanges.Exchange', autospec=True)
    exchange.map_balances = AsyncMock(side_effect=[
        {
            'spot': {
                'eth': Balance(),
                'btc': Balance(available=Decimal('1.0')),
            },
        },
        {
            'eth-btc': {
                'eth': Balance(available=Decimal('1.0')),
                'btc': Balance(),
            },
        }
    ])

    async with Wallet(exchanges=[exchange]) as wallet:
        balances = await wallet.map_balances(
            exchange='magicmock', accounts=['spot', 'isolated'], significant=True
        )

    assert balances == {
        'spot': {'btc': Balance(available=Decimal('1.0'))},
        'eth-btc': {'eth': Balance(available=Decimal('1.0'))},
    }
