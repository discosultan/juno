import asyncio
from contextlib import asynccontextmanager
from unittest.mock import MagicMock
from uuid import uuid4

from pytest_mock import MockerFixture

from juno.asyncio import stream_queue
from juno.common import Depth, ExchangeInfo, OrderResult, OrderStatus, OrderUpdate, Ticker
from juno.exchanges import Exchange


def mock_exchange(
    mocker: MockerFixture,
    client_id=str(uuid4()),
    exchange_info: ExchangeInfo = ExchangeInfo(),
    tickers: dict[str, Ticker] = {},
    depth: Depth.Snapshot = Depth.Snapshot(),
    stream_depth: list[Depth.Any] = [],
    stream_orders: list[OrderUpdate.Any] = [],
    place_order_result: OrderResult = OrderResult(time=0, status=OrderStatus.NEW),
    can_stream_balances: bool = True,
    can_stream_depth_snapshot: bool = True,
    can_stream_historical_earliest_candle: bool = True,
    can_stream_historical_candles: bool = True,
    can_stream_candles: bool = True,
    can_list_all_tickers: bool = True,
    can_margin_trade: bool = True,
    can_place_market_order: bool = True,
    can_place_market_order_quote: bool = True,
) -> MagicMock:
    exchange = mocker.MagicMock(Exchange, autospec=True)
    exchange.name = "magicmock"

    exchange.can_stream_balances = can_stream_balances
    exchange.can_stream_depth_snapshot = can_stream_depth_snapshot
    exchange.can_stream_historical_earliest_candle = can_stream_historical_earliest_candle
    exchange.can_stream_historical_candles = can_stream_historical_candles
    exchange.can_stream_candles = can_stream_candles
    exchange.can_list_all_tickers = can_list_all_tickers
    exchange.can_margin_trade = can_margin_trade
    exchange.can_place_market_order = can_place_market_order
    exchange.can_place_market_order_quote = can_place_market_order_quote

    exchange.generate_client_id.return_value = client_id
    exchange.get_exchange_info.return_value = exchange_info
    exchange.get_depth.return_value = depth
    exchange.map_tickers.return_value = tickers
    exchange.place_order.return_value = place_order_result

    stream_depth_queue: asyncio.Queue[Depth.Any] = asyncio.Queue()
    for d in stream_depth:
        stream_depth_queue.put_nowait(d)
    exchange.connect_stream_depth.side_effect = _connect_stream_queue(stream_depth_queue)
    exchange.stream_depth_queue = stream_depth_queue

    stream_orders_queue: asyncio.Queue[OrderUpdate.Any] = asyncio.Queue()
    for o in stream_orders:
        stream_orders_queue.put_nowait(o)
    exchange.connect_stream_orders.side_effect = _connect_stream_queue(stream_orders_queue)
    exchange.stream_orders_queue = stream_orders_queue

    return exchange


def _connect_stream_queue(queue):
    @asynccontextmanager
    async def inner(*args, **kwargs):
        yield stream_queue(queue)

    return inner


def _stream_values(values):
    yield from values
