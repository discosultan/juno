import asyncio

from juno.assets import AssetInfo, ExchangeInfo, Fees
from juno.assets.exchanges import Exchange
from juno.assets.filters import Filters
from juno.exchanges.kraken import Session, from_http_symbol


class Kraken(Exchange):
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
