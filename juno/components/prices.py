import asyncio
from decimal import Decimal
from typing import Dict, Iterable, List

from juno.asyncio import resolved_stream, zip_async
from juno.components import Chandler
from juno.exchanges import Exchange
from juno.math import floor_multiple
from juno.time import DAY_MS

_EXCHANGE_FIAT_ASSET_MAP = {
    'binance': 'usdt',
    'coinbase': 'eur',
}


class Prices:
    def __init__(self, chandler: Chandler, exchanges: List[Exchange]) -> None:
        self._chandler = chandler
        self._exchanges = exchanges

    async def map_fiat_daily_prices(
        self, exchange: str, assets: Iterable[str], start: int, end: int
    ) -> Dict[str, List[Decimal]]:
        start = floor_multiple(start, DAY_MS)
        end = floor_multiple(end, DAY_MS)

        result: Dict[str, List[Decimal]] = {}
        # Currently only supports calculating against BTC in coinbase.
        fiat_asset = _EXCHANGE_FIAT_ASSET_MAP[exchange]
        quote_fiat_prices = [c.close async for c in self._chandler.stream_candles(
            exchange, f'btc-{fiat_asset}', DAY_MS, start, end, fill_missing_with_last=True
        )]
        result['btc'] = quote_fiat_prices

        async def assign(asset: str) -> None:
            result[asset] = [c.close * p async for c, p in zip_async(
                self._chandler.stream_candles(
                    exchange, f'{asset}-btc', DAY_MS, start, end,
                    fill_missing_with_last=True
                ),
                resolved_stream(*quote_fiat_prices)
            )]
        await asyncio.gather(*(assign(a) for a in assets if a != 'btc'))

        return result
