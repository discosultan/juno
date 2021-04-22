from contextlib import asynccontextmanager
from decimal import Decimal
from time import time
from typing import Any, AsyncIterable, AsyncIterator, Optional

import juno.json as json
from juno.exchanges.gateio import Session, from_asset, from_timestamp, to_decimal, to_symbol
from juno.user import Balance, OrderResult, OrderStatus, OrderType, OrderUpdate
from juno.user.exchanges import Exchange
from juno.utils import short_uuid4


class GateIO(Exchange):
    def __init__(self, session: Session) -> None:
        self._session = session

    def generate_client_id(self) -> str:
        return short_uuid4()

    async def map_balances(self, account: str) -> dict[str, dict[str, Balance]]:
        assert account == 'spot'
        result = {}
        content = await self._session.request_signed_json('GET', '/api/v4/spot/accounts')
        result['spot'] = {
            from_asset(balance['currency']): Balance(
                available=Decimal(balance['available']),
                hold=Decimal(balance['locked']),
            ) for balance in content
        }
        return result

    @asynccontextmanager
    async def connect_stream_balances(
        self, account: str
    ) -> AsyncIterator[AsyncIterable[dict[str, Balance]]]:
        assert account == 'spot'
        channel = 'spot.balances'

        # https://www.gateio.pro/docs/apiv4/ws/index.html#client-subscription-9
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[dict[str, Balance]]:
            async for msg in ws:
                data = json.loads(msg.data)

                if data['channel'] != channel or data['event'] != 'update':
                    continue

                yield {
                    from_asset(b['currency']): Balance(
                        available=(available := Decimal(b['available'])),
                        hold=Decimal(b['total']) - available,
                    ) for b in data['result']
                }

        # TODO: unsubscribe
        async with self._session.ws_connect(_WS_URL) as ws:
            time_sec = int(time())
            event = 'subscribe'  # 'unsubscribe' for unsubscription
            await ws.send_json({
                'time': time_sec,
                'channel': channel,
                'event': event,
                'auth': self._gen_ws_sign(channel, event, time_sec),
            })
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
        assert account == 'spot'
        assert type_ in [OrderType.LIMIT, OrderType.LIMIT_MAKER]
        assert quote is None
        assert size is not None
        assert price is not None

        ot, tif = _to_order_type_and_time_in_force(type_, time_in_force)

        body: dict[str, Any] = {
            'currency_pair': to_symbol(symbol),
            'type': ot,
            'side': _to_side(side),
            'price': to_decimal(price),
            'amount': to_decimal(size),
        }
        if client_id is not None:
            body['text'] = f't-{client_id}'
        if tif is not None:
            body['time_in_force'] = tif

        async with self._session.request_signed(
            'POST', '/api/v4/spot/orders', body=body
        ) as response:
            if response.status == 400:
                error = await response.json()
                if error['label'] == 'POC_FILL_IMMEDIATELY':
                    raise OrderWouldBeTaker(error['message'])
            response.raise_for_status()
            content = await response.json()

        assert content['status'] != 'cancelled'

        return OrderResult(
            time=from_timestamp(content['create_time']),
            status=OrderStatus.NEW,
        )

    async def cancel_order(
        self,
        account: str,
        symbol: str,
        client_id: str,
    ) -> None:
        # NB! Custom client id will not be available anymore if the order has been up for more than
        # 30 min.
        assert account == 'spot'

        params = {
            'currency_pair': to_symbol(symbol),
        }

        async with self._session.request_signed(
            'DELETE',
            f'/api/v4/spot/orders/t-{client_id}',
            params=params,
        ) as response:
            if response.status == 400:
                content = await response.json()
                raise OrderMissing(content['message'])

            response.raise_for_status()

    @asynccontextmanager
    async def connect_stream_orders(
        self, account: str, symbol: str
    ) -> AsyncIterator[AsyncIterable[OrderUpdate.Any]]:
        assert account == 'spot'
        channel = 'spot.orders'

        # https://www.gateio.pro/docs/apiv4/ws/index.html#client-subscription-7
        async def inner(ws: AsyncIterable[Any]) -> AsyncIterable[OrderUpdate.Any]:
            async for msg in ws:
                data = json.loads(msg.data)

                if data['channel'] != channel or data['event'] != 'update':
                    continue

                for data in data['result']:
                    client_id = data['text'][2:]
                    event = data['event']
                    if event == 'put':
                        yield OrderUpdate.New(client_id=client_id)
                    elif event == 'update':
                        yield OrderUpdate.Match(
                            client_id=client_id,
                            fill=Fill.with_computed_quote(
                                price=Decimal(data['price']),
                                size=Decimal(data['amount']),
                                fee=Decimal(data['fee']),
                                fee_asset=from_asset(data['fee_currency']),
                            ),
                        )
                    elif event == 'finish':
                        time = from_timestamp(data['update_time'])
                        if data['left'] == '0':
                            yield OrderUpdate.Match(
                                client_id=client_id,
                                fill=Fill.with_computed_quote(
                                    price=Decimal(data['price']),
                                    size=Decimal(data['amount']),
                                    fee=Decimal(data['fee']),
                                    fee_asset=from_asset(data['fee_currency']),
                                ),
                            )
                            yield OrderUpdate.Done(
                                client_id=client_id,
                                time=time,
                            )
                        else:
                            yield OrderUpdate.Cancelled(
                                client_id=client_id,
                                time=time,
                            )
                    else:
                        raise NotImplementedError()

        # TODO: unsubscribe
        async with self._session.ws_connect(_WS_URL) as ws:
            time_sec = int(time())
            event = 'subscribe'  # 'unsubscribe' for unsubscription
            await ws.send_json({
                'time': time_sec,
                'channel': channel,
                'event': event,
                'payload': [to_symbol(symbol)],  # Can pass '!all' for all symbols.
                'auth': self._gen_ws_sign(channel, event, time_sec),
            })
            yield inner(ws)


def _to_order_type_and_time_in_force(
    type: OrderType, time_in_force: Optional[TimeInForce]
) -> tuple[str, Optional[str]]:
    ot = 'limit'
    tif = None

    if type not in [OrderType.LIMIT, OrderType.LIMIT_MAKER]:
        raise NotImplementedError()

    if type is OrderType.LIMIT_MAKER:
        assert time_in_force is None
        tif = 'poc'
    elif time_in_force is TimeInForce.IOC:
        tif = 'ioc'
    elif time_in_force is TimeInForce.GTC:
        tif = 'gtc'
    elif time_in_force is TimeInForce.FOK:
        raise NotImplementedError()

    return ot, tif


def _to_side(side: Side) -> str:
    if side is Side.BUY:
        return 'buy'
    if side is Side.SELL:
        return 'sell'
    raise NotImplementedError()
