from decimal import Decimal

from juno.utils import AbstractAsyncContextManager


class Service(AbstractAsyncContextManager):
    # TODO: bound to be out-of-date with the current syncing approach
    async def map_tickers(
        self,
        exchange: str,
        symbol_patterns: Optional[list[str]] = None,
        exclude_symbol_patterns: Optional[list[str]] = None,
        spot: Optional[bool] = None,
        cross_margin: Optional[bool] = None,
        isolated_margin: Optional[bool] = None,
    ) -> dict[str, Ticker]:
        exchange_info = self._synced_data[exchange][_Timestamped[ExchangeInfo]].item
        all_tickers = self._synced_data[exchange][_Timestamped[dict[str, Ticker]]].item

        result = ((s, t) for s, t in all_tickers.items())

        if symbol_patterns is not None:
            result = (
                (s, t) for s, t in result if any(fnmatch.fnmatch(s, p) for p in symbol_patterns)
            )
        if exclude_symbol_patterns:
            result = (
                (s, t) for s, t in result
                if not any(fnmatch.fnmatch(s, p) for p in exclude_symbol_patterns)
            )
        if spot is not None:
            result = (
                (s, t) for s, t in result
                if exchange_info.filters[s].spot == spot
            )
        if cross_margin is not None:
            result = (
                (s, t) for s, t in result
                if exchange_info.filters[s].cross_margin == cross_margin
            )
        if isolated_margin is not None:
            result = (
                (s, t) for s, t in result
                if exchange_info.filters[s].isolated_margin == isolated_margin
            )

        # Sorted by quote volume desc. Watch out when queried with different quote assets.
        return dict(sorted(result, key=lambda st: st[1].quote_volume, reverse=True))
