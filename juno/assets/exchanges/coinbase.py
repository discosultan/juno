from decimal import Decimal

from juno.assets import AssetInfo, ExchangeInfo, Fees
from juno.assets.exchanges import Exchange
from juno.assets.filters import Filters, Price, Size
from juno.exchanges.coinbase import Session, from_symbol


class Coinbase(Exchange):
    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_exchange_info(self) -> ExchangeInfo:
        # TODO: Fetch from exchange API if possible? Also has a more complex structure.
        # See https://support.pro.coinbase.com/customer/en/portal/articles/2945310-fees
        fees = {'__all__': Fees(maker=Decimal('0.005'), taker=Decimal('0.005'))}

        _, content = await self._session.public_request('GET', '/products')
        filters = {}
        for product in content:
            price_step = Decimal(product['quote_increment'])
            size_step = Decimal(product['base_increment'])
            filters[from_symbol(product['id'])] = Filters(
                base_precision=-size_step.normalize().as_tuple()[2],
                quote_precision=-price_step.normalize().as_tuple()[2],
                price=Price(
                    min=Decimal(product['min_market_funds']),
                    max=Decimal(product['max_market_funds']),
                    step=price_step,
                ),
                size=Size(
                    min=Decimal(product['base_min_size']),
                    max=Decimal(product['base_max_size']),
                    step=size_step,
                ),
            )

        return ExchangeInfo(
            assets={'__all__': AssetInfo(precision=8)},
            fees=fees,
            filters=filters,
        )
