import asyncio
from decimal import Decimal
from typing import Dict, Iterable, List

from juno.asyncio import resolved_stream, zip_async
from juno.components import Chandler
from juno.math import floor_multiple
from juno.time import DAY_MS


class Prices:
    def __init__(self, chandler: Chandler) -> None:
        self._chandler = chandler
        self._fiat_asset = 'eur'

    async def map_daily_fiat_prices(
        self, assets: Iterable[str], start: int, end: int
    ) -> Dict[str, List[Decimal]]:
        start = floor_multiple(start, DAY_MS)
        end = floor_multiple(end, DAY_MS)

        result: Dict[str, List[Decimal]] = {}
        # Currently only support calculating against BTC.
        quote_fiat_prices = [c.close async for c in self._chandler.stream_candles(
            'coinbase', f'btc-{self._fiat_asset}', DAY_MS, start, end, fill_missing_with_last=True
        )]
        result['btc'] = quote_fiat_prices

        async def assign(asset: str) -> None:
            result[asset] = [c.close * p async for c, p in zip_async(
                self._chandler.stream_candles(
                    'binance', f'{asset}-{self._fiat_asset}', DAY_MS, start, end,
                    fill_missing_with_last=True
                ),
                resolved_stream(*quote_fiat_prices)
            )]
        await asyncio.gather(*(assign(a) for a in assets))

        return result
