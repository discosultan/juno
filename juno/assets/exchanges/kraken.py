import asyncio
from decimal import Decimal

from juno.assets.filters import Filters
from juno.assets.models import AssetInfo, ExchangeInfo, Fees, Ticker
from juno.exchanges.kraken import Kraken as Session
from juno.exchanges.kraken import from_http_symbol, to_http_symbol

from .exchange import Exchange


class Kraken(Exchange):
    can_list_all_tickers: bool = False

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_exchange_info(self) -> ExchangeInfo:
        assets_res, symbols_res = await asyncio.gather(
            self._session.request_public('GET', '/0/public/Assets'),
            self._session.request_public('GET', '/0/public/AssetPairs'),
        )

        assets = {
            from_http_symbol(val['altname']): AssetInfo(precision=val['decimals'])
            for val in assets_res['result'].values()
        }

        fees, filters = {}, {}
        for val in symbols_res['result'].values():
            name = from_http_symbol(f'{val["base"][1:].lower()}-{val["quote"][1:].lower()}')
            # TODO: Take into account different fee levels. Currently only worst level.
            taker_fee = val['fees'][0][1] / 100
            maker_fees = val.get('fees_maker')
            fees[name] = Fees(
                maker=maker_fees[0][1] / 100 if maker_fees else taker_fee,
                taker=taker_fee
            )
            filters[name] = Filters(
                base_precision=val['lot_decimals'],
                quote_precision=val['pair_decimals'],
            )

        return ExchangeInfo(
            assets=assets,
            fees=fees,
            filters=filters,
        )

    async def map_tickers(self, symbols: list[str] = []) -> dict[str, Ticker]:
        if not symbols:
            raise ValueError('Empty symbols list not supported')

        data = {'pair': ','.join((to_http_symbol(s) for s in symbols))}

        res = await self._session.request_public('GET', '/0/public/Ticker', data=data)
        return {
            from_http_symbol(pair): Ticker(
                volume=Decimal(val['v'][1]),
                quote_volume=Decimal('0.0'),  # Not supported.
                price=Decimal(val['c'][0]),
            ) for pair, val in res['result'].items()
        }
