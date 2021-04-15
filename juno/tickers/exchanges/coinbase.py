from decimal import Decimal

from juno.exchanges.coinbase import Session, from_symbol
from juno.tickers import Ticker
from juno.tickers.exchanges import Exchange


class Coinbase(Exchange):
    # Capabilities.
    can_list_all_tickers: bool = False

    def __init__(self, session: Session) -> None:
        self._session = session

    async def map_tickers(self, symbols: list[str] = []) -> dict[str, Ticker]:
        # TODO: Use REST endpoint instead of WS here?
        # https://docs.pro.coinbase.com/#get-product-ticker
        # https://github.com/coinbase/coinbase-pro-node/issues/363#issuecomment-513876145
        if not symbols:
            raise ValueError('Empty symbols list not supported')

        tickers = {}
        async with self._ws.subscribe('ticker', ['ticker'], symbols) as ws:
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
