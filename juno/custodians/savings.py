import asyncio
import logging
from decimal import Decimal
from typing import Optional

from juno import Balance
from juno.components import User

from .custodian import Custodian

_log = logging.getLogger(__name__)

_TIMEOUT = 10.0


class Savings(Custodian):
    def __init__(self, user: User) -> None:
        self._user = user

    async def request_quote(self, exchange: str, asset: str, quote: Optional[Decimal]) -> Decimal:
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
        _log.info(f"redeeming {quote} worth of {asset} flexible savings product")
        products = await self._user.map_savings_products(exchange)

        product = products.get(asset)
        if product is None:
            _log.info(f"{asset} savings product not available; skipping")
            return

        async with self._user.sync_wallet(exchange, "spot") as wallet:
            await self._user.redeem_savings_product(exchange, product.product_id, quote)
            await asyncio.wait_for(
                _wait_for_wallet_updated_with(wallet, asset, quote),
                timeout=_TIMEOUT,
            )
        _log.info(f"redeemed {quote} worth of {asset} flexible savings product")

    async def release(self, exchange: str, asset: str, quote: Decimal) -> None:
        _log.info(f"purchasing {quote} worth of {asset} flexible savings product")
        products = await self._user.map_savings_products(exchange)

        product = products.get(asset)
        if product is None:
            _log.info(f"{asset} savings product not available; skipping")
            return

        async with self._user.sync_wallet(exchange, "spot") as wallet:
            await self._user.purchase_savings_product(exchange, product.product_id, quote)
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
