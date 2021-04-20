from decimal import Decimal

from juno.tickers import Ticker
from juno.tickers.exchanges import Exchange
from juno.utils import AbstractAsyncContextManager


class Service(AbstractAsyncContextManager):
    def __init__(
        self,
        exchanges: list[Exchange],
    ) -> None:
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}

    async def map_tickers(
        self,
        exchange: str,
        symbols: list[str],
    ) -> dict[str, Ticker]:
        result = await self._exchanges[exchange].map_tickers(symbols)

        # Sorted by quote volume desc. Watch out when queried with different quote assets.
        return dict(sorted(result.items(), key=lambda st: st[1].quote_volume, reverse=True))
