from decimal import Decimal

from juno.assets.filters import Filters, Price, Size
from juno.assets.models import AssetInfo, ExchangeInfo, Fees, Ticker
from juno.exchanges.coinbase import Coinbase as Session
from juno.exchanges.coinbase import from_symbol

from .exchange import Exchange


class Coinbase(Exchange):
    can_list_all_tickers: bool = False

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
            filters[product['id'].lower()] = Filters(
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

    async def map_tickers(self, symbols: list[str] = []) -> dict[str, Ticker]:
        # TODO: Use REST endpoint instead of WS here?
        # https://docs.pro.coinbase.com/#get-product-ticker
        # https://github.com/coinbase/coinbase-pro-node/issues/363#issuecomment-513876145
        if not symbols:
            raise ValueError('Empty symbols list not supported')

        tickers = {}
        async with self._session.ws.subscribe('ticker', ['ticker'], symbols) as ws:
            async for msg in ws:
                symbol = from_symbol(msg['product_id'])
                tickers[symbol] = Ticker(
                    volume=Decimal(msg['volume_24h']),  # TODO: incorrect?!
                    quote_volume=Decimal('0.0'),  # Not supported.
                    price=Decimal(msg['price']),
                )
                if len(tickers) == len(symbols):
                    break
        return tickers
