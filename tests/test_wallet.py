from decimal import Decimal

from juno import Balance
from juno.components import Wallet


async def test_get_balance(mocker) -> None:
    balance = Balance(available=Decimal('1.0'), hold=Decimal('0.0'))

    exchange = mocker.patch('juno.exchanges.Exchange', autospec=True)
    exchange.map_balances.return_value = {'spot': {'btc': balance}}

    async with Wallet(exchanges=[exchange]) as wallet:
        out_balance = await wallet.get_balance(
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

    async with Wallet(exchanges=[exchange]) as wallet:
        balances = await wallet.map_balances(
            exchange='magicmock', accounts=['spot', 'isolated'], significant=True
        )

    assert balances == {
        'spot': {'btc': Balance(available=Decimal('1.0'))},
        'eth-btc': {'eth': Balance(available=Decimal('1.0'))},
    }
