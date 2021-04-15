from decimal import Decimal

from juno.exchanges.kraken import Session, from_http_symbol, to_http_symbol
from juno.tickers import Ticker
from juno.tickers.exchanges import Exchange


class Kraken(Exchange):
    # Capabilities.
    can_list_all_tickers: bool = False

    def __init__(self, session: Session) -> None:
        self._session = session

    async def map_tickers(self, symbols: list[str] = []) -> dict[str, Ticker]:
        if not symbols:
            raise ValueError('Empty symbols list not supported')

        data = {'pair': ','.join((to_http_symbol(s) for s in symbols))}

        res = await self._request_public('GET', '/0/public/Ticker', data=data)
        return {
            from_http_symbol(pair): Ticker(
                volume=Decimal(val['v'][1]),
                quote_volume=Decimal('0.0'),  # Not supported.
                price=Decimal(val['c'][0]),
            ) for pair, val in res['result'].items()
        }
