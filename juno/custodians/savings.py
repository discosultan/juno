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


class Savings(Custodian):
    def __init__(self, user: User) -> None:
        self._user = user

    async def request_quote(
        self, exchange: str, asset: Asset, quote: Optional[Decimal]
    ) -> Decimal:
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

    async def acquire(self, exchange: str, asset: Asset, quote: Decimal) -> None:
        _log.info(f"redeeming {quote} worth of {asset} flexible savings product")

        product = await asyncio.wait_for(
            self._wait_for_product_status_purchasing(exchange, asset),
            timeout=_PRODUCT_TIMEOUT,
        )
        if product is None:
            _log.info(f"{asset} savings product not available; skipping")
            return

        async with self._user.sync_wallet(exchange, "spot") as wallet:
            await self._user.redeem_savings_product(exchange, product.product_id, quote)
            await asyncio.wait_for(
                self._wait_for_wallet_updated_with(wallet, asset, quote),
                timeout=_BALANCE_TIMEOUT,
            )

        _log.info(f"redeemed {quote} worth of {asset} flexible savings product")

    async def release(self, exchange: str, asset: Asset, quote: Decimal) -> None:
        _log.info(f"purchasing {quote} worth of {asset} flexible savings product")

        product = await asyncio.wait_for(
            self._wait_for_product_status_purchasing(exchange, asset),
            timeout=_PRODUCT_TIMEOUT,
        )
        if product is None:
            _log.info(f"{asset} savings product not available; skipping")
            return

        async with self._user.sync_wallet(exchange, "spot") as wallet:
            await self._user.purchase_savings_product(exchange, product.product_id, quote)
            savings_asset = f"ld{asset}"
            await asyncio.wait_for(
                self._wait_for_wallet_updated_with(wallet, savings_asset, quote),
                timeout=_BALANCE_TIMEOUT,
            )

        _log.info(f"purchased {quote} worth of {asset} flexible savings product")

    async def _wait_for_wallet_updated_with(
        self, wallet: User.WalletSyncContext, asset: Asset, quote: Decimal
    ) -> None:
        while True:
            await wallet.updated.wait()
            if wallet.balances.get(asset, Balance()).available >= quote:
                return

    async def _wait_for_product_status_purchasing(
        self, exchange: str, asset: Asset
    ) -> Optional[SavingsProduct]:
        # A product can be in status "PURCHASING" or "PREHEATING". "PURCHASING" is when the product
        # is available. "PREHEATING" means the product is being processed. This happens usually at
        # 23:50 - 00:10 UTC.
        # https://dev.binance.vision/t/failure-to-fast-redeem-a-flexible-savings-product-right-after-midnight-00-00-utc/5785
        while True:
            products = await self._user.map_savings_products(exchange)

            product = products.get(asset)
            if product is None:
                return None

            if product.status == "PREHEATING":
                _log.info(
                    f"{asset} savings product is preheating; waiting a minute before retrying"
                )
                await asyncio.sleep(60.0)
            elif product.status == "PURCHASING":
                return product
            else:
                raise Exception(f"Unknown {asset} savings product status {product.status}")
