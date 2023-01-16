import asyncio
import logging
from decimal import Decimal
from typing import Optional

from juno import Asset, Balance, SavingsProduct
from juno.components import User

from .custodian import Custodian

_log = logging.getLogger(__name__)

_BALANCE_TIMEOUT = 10.0
_PRODUCT_TIMEOUT = 30 * 60.0
_EMPTY_BALANCE = Balance()


class Savings(Custodian):
    def __init__(self, user: User) -> None:
        self._user = user

    async def request(self, exchange: str, asset: Asset, amount: Optional[Decimal]) -> Decimal:
        # On Binance, a flexible savings asset is indicated with an "ld"-prefix. It stands for
        # "lending daily".
        savings_asset = f"ld{asset}"
        available_amount = (
            await self._user.get_balance(exchange=exchange, account="spot", asset=savings_asset)
        ).available

        if amount is None:
            _log.info(f"amount not specified; using available {available_amount} {asset}")
            return available_amount

        if available_amount < amount:
            raise ValueError(
                f"Requesting trading with {amount} {asset} but only {available_amount} available"
            )

        return amount

    async def acquire(self, exchange: str, asset: Asset, amount: Decimal) -> None:
        _log.info(f"redeeming {amount} worth of {asset} flexible savings product")

        product = await asyncio.wait_for(
            self._wait_for_product_status_purchasing(exchange, asset),
            timeout=_PRODUCT_TIMEOUT,
        )
        if product is None:
            _log.info(f"{asset} savings product not available; skipping")
            return
        if product.status == "END":
            _log.info(f"{asset} savings product has ended; skipping")
            return

        async with self._user.sync_wallet(exchange, "spot") as wallet:
            savings_asset = _savings_asset(asset)
            savings_amount = wallet.balances.get(savings_asset, _EMPTY_BALANCE).available
            if savings_amount == 0:
                _log.info("nothing to redeem; savings balance 0")
                return

            await self._user.redeem_savings_product(exchange, product.product_id, savings_amount)
            await asyncio.wait_for(
                self._wait_for_wallet_updated_with(wallet, asset, amount),
                timeout=_BALANCE_TIMEOUT,
            )
            assert wallet.balances.get(savings_asset, _EMPTY_BALANCE).available == 0

        _log.info(f"redeemed {savings_amount} worth of {asset} flexible savings product")

    async def release(self, exchange: str, asset: Asset, amount: Decimal) -> None:
        _log.info(f"purchasing {amount} worth of {asset} flexible savings product")

        product = await asyncio.wait_for(
            self._wait_for_product_status_purchasing(exchange, asset),
            timeout=_PRODUCT_TIMEOUT,
        )
        if product is None:
            _log.info(f"{asset} savings product not available; skipping")
            return
        if product.status == "END":
            _log.info(f"{asset} savings product has ended; skipping")
            return

        savings_amount = amount

        global_available_product = product.limit - product.purchased_amount
        if amount > global_available_product:
            _log.info(f"only {global_available_product} available globally")
            savings_amount = global_available_product

        if amount > product.limit_per_user:
            _log.info(f"only {product.limit_per_user} available per user")
            savings_amount = product.limit_per_user

        if savings_amount < product.min_purchase_amount:
            _log.info(
                f"{savings_amount} less than minimum purchase amount "
                f"{product.min_purchase_amount}; skipping"
            )
            return

        async with self._user.sync_wallet(exchange, "spot") as wallet:
            await self._user.purchase_savings_product(exchange, product.product_id, savings_amount)
            savings_asset = _savings_asset(asset)
            await asyncio.wait_for(
                self._wait_for_wallet_updated_with(wallet, savings_asset, savings_amount),
                timeout=_BALANCE_TIMEOUT,
            )
            assert wallet.balances.get(asset, _EMPTY_BALANCE).available >= amount - savings_amount

        _log.info(f"purchased {savings_amount} worth of {asset} flexible savings product")

    async def _wait_for_wallet_updated_with(
        self,
        wallet: User.WalletSyncContext,
        asset: Asset,
        amount: Decimal,
    ) -> None:
        while True:
            await wallet.updated.wait()
            if wallet.balances.get(asset, _EMPTY_BALANCE).available >= amount:
                return

    async def _wait_for_product_status_purchasing(
        self,
        exchange: str,
        asset: Asset,
    ) -> Optional[SavingsProduct]:
        # A product can be in status "PURCHASING", "PREHEATING" or "END". "PURCHASING" is when the
        # product is available. "PREHEATING" means the product is being processed. This happens
        # usually at 23:50 - 00:10 UTC.
        # https://dev.binance.vision/t/failure-to-fast-redeem-a-flexible-savings-product-right-after-midnight-00-00-utc/5785
        while True:
            products = await self._user.map_savings_products(exchange=exchange, asset=asset)

            product = products.get(asset)
            if product is None:
                return None

            if product.status in "PREHEATING":
                _log.info(
                    f"{asset} savings product is preheating; waiting a minute before retrying"
                )
                await asyncio.sleep(60.0)
            elif product.status == "PURCHASING":
                return product
            elif product.status == "END":
                raise Exception(f"{asset} savings product has ended")
            else:
                raise Exception(f"Unknown {asset} savings product status {product.status}")


def _savings_asset(asset: Asset) -> Asset:
    return f"ld{asset}"
