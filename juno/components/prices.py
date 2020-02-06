from decimal import Decimal
from typing import Dict, Iterable, List

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
        for _asset in assets:
            pass
        return result
