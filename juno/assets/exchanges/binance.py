import asyncio
import logging
from decimal import Decimal

from juno.assets import AssetInfo, BorrowInfo, ExchangeInfo, Fees
from juno.assets.exchanges import Exchange
from juno.assets.filters import Filters, MinNotional, PercentPrice, Price, Size
from juno.exchanges.binance import Session, from_http_symbol
from juno.time import MIN_MS

_log = logging.getLogger(__name__)


class Binance(Exchange):
    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_exchange_info(self) -> ExchangeInfo:
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/wapi-api.md#trade-fee-user_data
        # https://github.com/binance-exchange/binance-official-api-docs/blob/master/rest-api.md#exchange-information
        fees_ret, filters_ret, isolated_pairs, margin_ret, isolated_ret = await asyncio.gather(
            self._api_request('GET', '/sapi/v1/asset/tradeFee', security=_SEC_USER_DATA),
            self._api_request('GET', '/api/v3/exchangeInfo', weight=10),
            self._list_symbols(isolated=True),
            self._request_json(
                method='GET',
                url='https://www.binance.com/gateway-api/v1/friendly/margin/vip/spec/list-all',
            ),
            self._request_json(
                method='GET',
                url='https://www.binance.com/gateway-api/v1/public/isolated-margin/pair/vip-level',
            )
        )
        _, fees_content = fees_ret
        _, filters_content = filters_ret
        _, margin_content = margin_ret
        _, isolated_content = isolated_ret

        # Process fees.
        fees = {
            from_http_symbol(fee['symbol']):
            Fees(maker=Decimal(fee['makerCommission']), taker=Decimal(fee['takerCommission']))
            for fee in fees_content
        }

        # Process borrow info.
        # The data below is not available through official Binance API. We can get borrow limit but
        # there is no way to get interest rate.
        borrow_info = {
            'margin': {
                a['assetName'].lower(): BorrowInfo(
                    daily_interest_rate=Decimal(s['dailyInterestRate']),
                    limit=Decimal(s['borrowLimit']),
                ) for a, s in ((a, a['specs'][0]) for a in margin_content['data'])
            },
        }
        for p in isolated_content['data']:
            base = p['base']
            base_asset = base['assetName'].lower()
            quote = p['quote']
            quote_asset = quote['assetName'].lower()

            base_levels = base['levelDetails']
            if len(base_levels) == 0:
                _log.info(
                    f'no isolated margin borrow info for {base_asset}-{quote_asset} '
                    f'{base_asset} asset'
                )
                continue
            base_details = base_levels[0]

            quote_levels = quote['levelDetails']
            if len(quote_levels) == 0:
                _log.info(
                    f'no isolated margin borrow info for {base_asset}-{quote_asset} '
                    f'{quote_asset} asset'
                )
                continue
            quote_details = quote_levels[0]

            borrow_info[f'{base_asset}-{quote_asset}'] = {
                base_asset: BorrowInfo(
                    daily_interest_rate=Decimal(base_details['interestRate']),
                    limit=Decimal(base_details['maxBorrowable']),
                ),
                quote_asset: BorrowInfo(
                    daily_interest_rate=Decimal(quote_details['interestRate']),
                    limit=Decimal(quote_details['maxBorrowable']),
                ),
            }

        # Process symbol info.
        isolated_pairs_set = set(isolated_pairs)
        filters = {}
        for symbol_info in filters_content['symbols']:
            for f in symbol_info['filters']:
                t = f['filterType']
                if t == 'PRICE_FILTER':
                    price = f
                elif t == 'PERCENT_PRICE':
                    percent_price = f
                elif t == 'LOT_SIZE':
                    lot_size = f
                elif t == 'MIN_NOTIONAL':
                    min_notional = f
            assert all((price, percent_price, lot_size, min_notional))

            symbol = f"{symbol_info['baseAsset'].lower()}-{symbol_info['quoteAsset'].lower()}"
            filters[symbol] = Filters(
                price=Price(
                    min=Decimal(price['minPrice']),
                    max=Decimal(price['maxPrice']),
                    step=Decimal(price['tickSize'])
                ),
                percent_price=PercentPrice(
                    multiplier_up=Decimal(percent_price['multiplierUp']),
                    multiplier_down=Decimal(percent_price['multiplierDown']),
                    avg_price_period=percent_price['avgPriceMins'] * MIN_MS
                ),
                size=Size(
                    min=Decimal(lot_size['minQty']),
                    max=Decimal(lot_size['maxQty']),
                    step=Decimal(lot_size['stepSize'])
                ),
                min_notional=MinNotional(
                    min_notional=Decimal(min_notional['minNotional']),
                    apply_to_market=min_notional['applyToMarket'],
                    avg_price_period=percent_price['avgPriceMins'] * MIN_MS
                ),
                base_precision=symbol_info['baseAssetPrecision'],
                quote_precision=symbol_info['quoteAssetPrecision'],
                spot='SPOT' in symbol_info['permissions'],
                cross_margin='MARGIN' in symbol_info['permissions'],
                isolated_margin=(symbol in isolated_pairs_set) and (symbol in borrow_info),
            )

        return ExchangeInfo(
            assets={'__all__': AssetInfo(precision=8)},
            fees=fees,
            filters=filters,
            borrow_info=borrow_info,
        )
