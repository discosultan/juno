from decimal import Decimal

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
