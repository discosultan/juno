from decimal import Decimal

from juno import Balance
from juno.components import User


async def test_get_balance(mocker) -> None:
    balance = Balance(available=Decimal('1.0'), hold=Decimal('0.0'))

    exchange = mocker.patch('juno.exchanges.Exchange', autospec=True)
    exchange.map_balances.return_value = {'spot': {'btc': balance}}

    async with User(exchanges=[exchange]) as user:
        out_balance = await user.get_balance(
            exchange='magicmock', account='spot', asset='btc'
        )

    assert out_balance == balance


async def test_map_all_significant_balances(mocker) -> None:
    exchange = mocker.patch('juno.exchanges.Exchange', autospec=True)
    exchange.map_balances.side_effect = [
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
    ]

    async with User(exchanges=[exchange]) as user:
        balances = await user.map_balances(
            exchange='magicmock', accounts=['spot', 'isolated'], significant=True
        )

    assert balances == {
        'spot': {'btc': Balance(available=Decimal('1.0'))},
        'eth-btc': {'eth': Balance(available=Decimal('1.0'))},
    }


async def test_map_all_isolated(mocker) -> None:
    exchange = mocker.patch('juno.exchanges.Exchange', autospec=True)
    exchange.map_balances.return_value = {
        'eth-btc': {
            'eth': Balance(available=Decimal('1.0')),
            'btc': Balance(available=Decimal('2.0')),
        },
        'ltc-btc': {
            'ltc': Balance(),
            'btc': Balance(),
        },
    }

    async with User(exchanges=[exchange]) as user:
        balances = await user.map_balances(exchange='magicmock', accounts=['eth-btc'])

    assert balances == {
        'eth-btc': {
            'eth': Balance(available=Decimal('1.0')),
            'btc': Balance(available=Decimal('2.0')),
        },
    }
