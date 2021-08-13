import asyncio
import logging
from decimal import Decimal
from typing import Optional

from juno import Balance
from juno.components import User
from juno.exchanges import Binance, Exchange

from .custodian import Custodian

_log = logging.getLogger(__name__)

_TIMEOUT = 10.0


class Savings(Custodian):
    def __init__(self, user: User, exchanges: list[Exchange]) -> None:
        self._user = user
        self._binance = next(e for e in exchanges if isinstance(e, Binance))

    async def request_quote(self, exchange: str, asset: str, quote: Optional[Decimal]) -> Decimal:
        if exchange != "binance":
            raise NotImplementedError()

        # On Binance, a flexible savings asset is indicated with an "ld"-prefix. It stands for
        # "lending daily".
        savings_asset = f"ld{asset}"
        available_quote = (
            await self._user.get_balance(exchange=exchange, account="spot", asset=savings_asset)
        ).available

        if quote is None:
            _log.info(f"quote not specified; using available {available_quote} {asset}")
            return available_quote

        if available_quote < quote:
            raise ValueError(
                f"Requesting trading with {quote} {asset} but only {available_quote} available"
            )

        return quote

    async def acquire(self, exchange: str, asset: str, quote: Decimal) -> None:
        if exchange != "binance":
            raise NotImplementedError()

        products = await self._binance.map_flexible_products()

        if asset not in products:
            _log.info(f"{asset} savings product not available; skipping")
            return

        async with self._user.sync_wallet(exchange, "spot") as wallet:
            await self._binance.redeem_flexible_product(products[asset].product_id, quote)
            await asyncio.wait_for(
                _wait_for_wallet_updated_with(wallet, asset, quote),
                timeout=_TIMEOUT,
            )
        _log.info(f"redeemed {quote} worth of {asset} flexible savings product")

    async def release(self, exchange: str, asset: str, quote: Decimal) -> None:
        if exchange != "binance":
            raise NotImplementedError()

        products = await self._binance.map_flexible_products()

        if asset not in products:
            _log.info(f"{asset} savings product not available; skipping")
            return

        async with self._user.sync_wallet(exchange, "spot") as wallet:
            await self._binance.purchase_flexible_product(products[asset].product_id, quote)
            savings_asset = f"ld{asset}"
            await asyncio.wait_for(
                _wait_for_wallet_updated_with(wallet, savings_asset, quote),
                timeout=_TIMEOUT,
            )
        _log.info(f"purchased {quote} worth of {asset} flexible savings product")


async def _wait_for_wallet_updated_with(
    wallet: User.WalletSyncContext, asset: str, quote: Decimal
) -> None:
    while True:
        await wallet.updated.wait()
        if wallet.balances.get(asset, Balance()).available >= quote:
            return
