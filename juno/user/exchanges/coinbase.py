from contextlib import asynccontextmanager
from decimal import Decimal
from time import time
from typing import Any, AsyncIterable, AsyncIterator, Optional

import juno.json as json
from juno.exchanges.coinbase import Session, from_asset, from_timestamp, to_decimal, to_symbol
from juno.math import round_half_up
from juno.user import Balance, OrderResult, OrderStatus, OrderType, OrderUpdate
from juno.user.exchanges import Exchange
from juno.utils import short_uuid4


class Coinbase(Exchange):
    def __init__(self, session: Session) -> None:
        self._session = session

    async def map_balances(self, account: str) -> dict[str, dict[str, Balance]]:
        result = {}
        if account == 'spot':
            _, content = await self._private_request('GET', '/accounts')
            result['spot'] = {
                b['currency'].lower(): Balance(
                    available=Decimal(b['available']), hold=Decimal(b['hold'])
                ) for b in content
            }
        else:
            raise NotImplementedError()
        return result

    @asynccontextmanager
    async def connect_stream_orders(
        self, account: str, symbol: str
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        assert account == 'spot'

        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[OrderUpdate.Any]:
            base_asset, quote_asset = unpack_assets(symbol)
            async for data in ws:
                type_ = data['type']
                if type_ == 'received':
                    client_id = data['client_oid']
                    self._order_id_to_client_id[data['order_id']] = client_id
                    yield OrderUpdate.New(
                        client_id=client_id,
                    )
                elif type_ == 'done':
                    reason = data['reason']
                    order_id = data['order_id']
                    client_id = self._order_id_to_client_id[order_id]
                    # TODO: Should be paginated.
                    _, content = await self._private_request('GET', f'/fills?order_id={order_id}')
                    for fill in content:
                        # TODO: Coinbase fee is always returned in quote asset.
                        # TODO: Coinbase does not return quote, so we need to calculate it;
                        # however, we need to know quote precision and rounding rules for that.
                        # TODO: They seem to take fee in addition to specified size (not extract
                        # from size).
                        assert symbol == 'btc-eur'
                        quote_precision = 2
                        base_precision = 8
                        price = Decimal(fill['price'])
                        size = Decimal(fill['size'])
                        fee_quote = round_half_up(Decimal(fill['fee']), quote_precision)
                        fee_size = round_half_up(Decimal(fill['fee']) / price, base_precision)
                        yield OrderUpdate.Match(
                            client_id=client_id,
                            fill=Fill.with_computed_quote(
                                price=price,
                                size=size + fee_size,
                                fee=fee_size if fill['side'] == 'buy' else fee_quote,
                                fee_asset=base_asset if fill['side'] == 'buy' else quote_asset,
                                precision=quote_precision,
                            ),
                        )
                    if reason == 'filled':
                        yield OrderUpdate.Done(
                            time=from_timestamp(data['time']),
                            client_id=client_id,
                        )
                    elif reason == 'canceled':
                        yield OrderUpdate.Cancelled(
                            time=from_timestamp(data['time']),
                            client_id=client_id,
                        )
                    else:
                        raise NotImplementedError(data)
                elif type_ in ['open', 'match']:
                    pass
                else:
                    raise NotImplementedError(data)

        async with self._ws.subscribe(
            'user', ['received', 'open', 'match', 'done'], [symbol]
        ) as ws:
            yield inner(ws)

    async def place_order(
        self,
        account: str,
        symbol: str,
        side: Side,
        type_: OrderType,
        size: Optional[Decimal] = None,
        quote: Optional[Decimal] = None,
        price: Optional[Decimal] = None,
        time_in_force: Optional[TimeInForce] = None,
        client_id: Optional[str] = None,
    ) -> OrderResult:
        # https://docs.pro.coinbase.com/#place-a-new-order
        if account != 'spot':
            raise NotImplementedError()
        if type_ not in [OrderType.MARKET, OrderType.LIMIT, OrderType.LIMIT_MAKER]:
            # Supports stop orders through params.
            raise NotImplementedError()

        data: dict[str, Any] = {
            'type': 'market' if type_ is OrderType.MARKET else 'limit',
            'side': 'buy' if side is Side.BUY else 'sell',
            'product_id': to_symbol(symbol),
        }
        if size is not None:
            data['size'] = _to_decimal(size)
        if quote is not None:
            data['funds'] = _to_decimal(quote)
        if price is not None:
            data['price'] = _to_decimal(price)
        if time_in_force is not None:
            data['time_in_force'] = _to_time_in_force(time_in_force)
        if client_id is not None:
            data['client_oid'] = client_id
        if type_ is OrderType.LIMIT_MAKER:
            data['post_only'] = True

        response, content = await self._private_request('POST', '/orders', data=data)

        if response.status == 400:
            raise BadOrder(content['message'])

        # Does not support returning fills straight away. Need to listen through WS.
        return OrderResult(status=OrderStatus.NEW, time=_from_datetime(content['created_at']))

    async def cancel_order(
        self,
        account: str,
        symbol: str,
        client_id: str,
    ) -> None:
        if account != 'spot':
            raise NotImplementedError()
        response, content = await self._private_request('DELETE', f'/orders/client:{client_id}', {
            'product_id': _to_product(symbol),
        })
        if response.status == 404:
            raise OrderMissing(content['message'])


def _to_time_in_force(time_in_force: TimeInForce) -> str:
    if time_in_force is TimeInForce.GTC:
        return 'GTC'
    # elif time_in_force is TimeInForce.GTT:
    #     return 'GTT'
    elif time_in_force is TimeInForce.FOK:
        return 'FOK'
    elif time_in_force is TimeInForce.IOC:
        return 'IOC'
    raise NotImplementedError()


def _from_order_status(status: str) -> OrderStatus:
    if status == 'pending':
        return OrderStatus.NEW
    elif status == 'done':
        return OrderStatus.FILLED
    raise NotImplementedError()
