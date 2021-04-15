from decimal import Decimal

from juno.assets import ExchangeInfo, Fees
from juno.assets.exchanges import Exchange
from juno.assets.filters import Filters, Price, Size
from juno.exchanges.gateio import Session, from_symbol


class GateIO(Exchange):
    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_exchange_info(self) -> ExchangeInfo:
        # https://www.gate.io/docs/apiv4/en/index.html#list-all-currency-pairs-supported
        content = await self._session.request_json('GET', '/api/v4/spot/currency_pairs')

        fees, filters = {}, {}
        for pair in (c for c in content if c['trade_status'] == 'tradable'):
            symbol = from_symbol(pair['id'])
            # TODO: Take into account different fee levels. Currently only worst level.
            fee = Decimal(pair['fee']) / 100
            fees[symbol] = Fees(maker=fee, taker=fee)
            filters[symbol] = Filters(
                base_precision=pair['precision'],
                quote_precision=pair['amount_precision'],
                size=Size(
                    min=(
                        Decimal('0.0') if (min_base_amount := pair.get('min_base_amount')) is None
                        else Decimal(min_base_amount)
                    ),
                ),
                price=Price(
                    min=(
                        Decimal('0.0')
                        if (min_quote_amount := pair.get('min_quote_amount')) is None
                        else Decimal(min_quote_amount)
                    ),
                )
            )

        return ExchangeInfo(
            fees=fees,
            filters=filters,
        )
