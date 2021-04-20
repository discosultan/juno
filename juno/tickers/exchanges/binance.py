from decimal import Decimal

from juno.exchanges.binance import Session, from_http_symbol, to_http_symbol
from juno.tickers import Ticker
from juno.tickers.exchanges import Exchange


class Binance(Exchange):
    # Capabilities.
    can_list_all_tickers: bool = True

    def __init__(self, session: Session) -> None:
        self._session = session

    async def map_tickers(self, symbols: list[str] = []) -> dict[str, Ticker]:
        if len(symbols) > 1:
            raise NotImplementedError()

        data = {'symbol': to_http_symbol(symbols[0])} if symbols else None
        weight = 1 if symbols else 40
        _, content = await self._session.api_request(
            'GET', '/api/v3/ticker/24hr', data=data, weight=weight
        )
        response_data = [content] if symbols else content
        return {
            from_http_symbol(t['symbol']): Ticker(
                volume=Decimal(t['volume']),
                quote_volume=Decimal(t['quoteVolume']),
                price=Decimal(t['lastPrice']),
            ) for t in response_data
        }
