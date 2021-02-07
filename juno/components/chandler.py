from __future__ import annotations

import asyncio
import itertools
import logging
import sys
from contextlib import AsyncExitStack
from decimal import Decimal
from typing import AsyncIterable, Callable, Iterable, Optional

from tenacity import Retrying, before_sleep_log, retry_if_exception_type

from juno import Candle, ExchangeException
from juno.asyncio import first_async, list_async, stream_with_timeout
from juno.exchanges import Exchange
from juno.itertools import generate_missing_spans
from juno.math import ceil_multiple, floor_multiple
from juno.storages import Storage
from juno.tenacity import stop_after_attempt_with_reset, wait_none_then_exponential
from juno.time import MAX_TIME_MS, strfinterval, strfspan, strftimestamp, time_ms
from juno.utils import key, unpack_assets

from .trades import Trades

_log = logging.getLogger(__name__)

CANDLE_KEY = Candle.__name__.lower()
FIRST_CANDLE_KEY = f'first_{CANDLE_KEY}'


class Chandler:
    def __init__(
        self,
        storage: Storage,
        exchanges: list[Exchange],
        trades: Optional[Trades] = None,
        get_time_ms: Callable[[], int] = time_ms,
        storage_batch_size: int = 1000,
        earliest_exchange_start: int = 1293840000000,  # 2011-01-01
    ) -> None:
        assert storage_batch_size > 0

        self._storage = storage
        self._exchanges = {type(e).__name__.lower(): e for e in exchanges}
        self._trades = trades
        self._get_time_ms = get_time_ms
        self._storage_batch_size = storage_batch_size
        self._earliest_exchange_start = earliest_exchange_start

    async def list_candles(
        self,
        exchange: str,
        symbol: str,
        interval: int,
        start: int,
        end: int = MAX_TIME_MS,
        closed: bool = True,
        fill_missing_with_last: bool = False,
        simulate_open_from_interval: Optional[int] = None,
        exchange_timeout: Optional[float] = None,
    ) -> list[Candle]:
        return await list_async(self.stream_candles(
            exchange, symbol, interval, start, end, closed, fill_missing_with_last,
            simulate_open_from_interval, exchange_timeout
        ))

    async def stream_candles(
        self,
        exchange: str,
        symbol: str,
        interval: int,
        start: int,
        end: int = MAX_TIME_MS,
        closed: bool = True,
        fill_missing_with_last: bool = False,
        simulate_open_from_interval: Optional[int] = None,
        exchange_timeout: Optional[float] = None,
    ) -> AsyncIterable[Candle]:
        if simulate_open_from_interval is None:
            async for candle in self._stream_candles(
                exchange, symbol, interval, start, end, closed, fill_missing_with_last,
                exchange_timeout
            ):
                yield candle
        else:
            assert simulate_open_from_interval < interval
            assert interval % simulate_open_from_interval == 0
            assert closed
            assert fill_missing_with_last

            main_stream = self._stream_candles(
                exchange, symbol, interval, start, end, True, True, exchange_timeout
            ).__aiter__()
            side_stream = self._stream_candles(
                exchange, symbol, simulate_open_from_interval, start, end, True, True,
                exchange_timeout
            ).__aiter__()
            side_current = start
            side_end = start + interval
            side_open = None
            side_high = Decimal('0.0')
            side_low = Decimal('inf')
            side_volume = Decimal('0.0')
            while True:
                while side_current < side_end - simulate_open_from_interval:
                    try:
                        sc = await side_stream.__anext__()
                    except StopAsyncIteration:
                        break
                    if side_open is None:
                        side_open = sc.open
                    side_high = max(side_high, sc.high)
                    side_low = min(side_low, sc.low)
                    side_volume += sc.volume
                    yield Candle(
                        time=sc.time,
                        open=side_open,
                        high=side_high,
                        low=side_low,
                        close=sc.close,
                        volume=side_volume,
                        closed=False,
                    )
                    side_current = sc.time + simulate_open_from_interval
                try:
                    yield await main_stream.__anext__()
                    # Discard one from side.
                    await side_stream.__anext__()
                    side_end += interval
                    side_open = None
                    side_high = Decimal('0.0')
                    side_low = Decimal('inf')
                    side_volume = Decimal('0.0')
                except StopAsyncIteration:
                    break

    async def _stream_candles(
        self,
        exchange: str,
        symbol: str,
        interval: int,
        start: int,
        end: int,
        closed: bool,
        fill_missing_with_last: bool,
        exchange_timeout: Optional[float],
    ) -> AsyncIterable[Candle]:
        """Tries to stream candles for the specified range from local storage. If candles don't
        exist, streams them from an exchange and stores to local storage."""
        start = floor_multiple(start, interval)
        end = floor_multiple(end, interval)
        shard = key(exchange, symbol, interval)
        candle_msg = f'{exchange} {symbol} {strfinterval(interval)} candle(s)'

        _log.info(f'checking for existing {candle_msg} in local storage')
        existing_spans = await list_async(
            self._storage.stream_time_series_spans(
                shard=shard,
                key=CANDLE_KEY,
                start=start,
                end=end,
            )
        )
        missing_spans = list(generate_missing_spans(start, end, existing_spans))

        spans = (
            [(a, b, True) for a, b in existing_spans]
            + [(a, b, False) for a, b in missing_spans]
        )
        spans.sort(key=lambda s: s[0])

        last_closed_candle: Optional[Candle] = None
        for span_start, span_end, exist_locally in spans:
            period_msg = f'{strfspan(span_start, span_end)}'
            if exist_locally:
                _log.info(f'local {candle_msg} exist between {period_msg}')
                stream = self._storage.stream_time_series(
                    shard=shard,
                    key=CANDLE_KEY,
                    type_=Candle,
                    start=span_start,
                    end=span_end,
                )
            else:
                _log.info(f'missing {candle_msg} between {period_msg}')
                stream = self._stream_and_store_exchange_candles(
                    exchange, symbol, interval, span_start, span_end, exchange_timeout
                )
            async for candle in stream:
                if (
                    not last_closed_candle
                    and candle.closed
                    and (num_missed := (candle.time - start) // interval) > 0
                ):
                    _log.warning(
                        f'missed {num_missed} {candle_msg} from the start '
                        f'{strftimestamp(start)}; current candle {candle}'
                    )

                if (
                    last_closed_candle
                    and (time_diff := candle.time - last_closed_candle.time) >= interval * 2
                ):
                    num_missed = time_diff // interval - 1
                    _log.warning(
                        f'missed {num_missed} {candle_msg}; last closed candle '
                        f'{last_closed_candle}; current candle {candle}'
                    )
                    if fill_missing_with_last:
                        _log.info(f'filling {num_missed} missed {candle_msg} with last values')
                        for i in range(1, num_missed + 1):
                            yield Candle(
                                time=last_closed_candle.time + i * interval,
                                # open=last_closed_candle.open,
                                # high=last_closed_candle.high,
                                # low=last_closed_candle.low,
                                # close=last_closed_candle.close,
                                # volume=last_closed_candle.volume,
                                open=last_closed_candle.close,
                                high=last_closed_candle.close,
                                low=last_closed_candle.close,
                                close=last_closed_candle.close,
                                volume=Decimal('0.0'),
                                closed=True,
                            )
                if not closed or candle.closed:
                    yield candle
                if candle.closed:
                    last_closed_candle = candle

        if last_closed_candle and (time_diff := end - last_closed_candle.time) >= interval * 2:
            num_missed = time_diff // interval - 1
            _log.warning(
                f'missed {num_missed} {candle_msg} from the end {strftimestamp(end)}; '
                f'current candle {last_closed_candle}'
            )
        elif not last_closed_candle:
            _log.warning(f'missed all {candle_msg} between {strfspan(start, end)}')

    async def _stream_and_store_exchange_candles(
        self, exchange: str, symbol: str, interval: int, start: int, end: int,
        exchange_timeout: Optional[float]
    ) -> AsyncIterable[Candle]:
        shard = key(exchange, symbol, interval)
        # Note that we need to use a context manager based retrying because retry decorators do not
        # work with async generator functions.
        for attempt in Retrying(
            stop=stop_after_attempt_with_reset(8, 300),
            wait=wait_none_then_exponential(),
            retry=retry_if_exception_type(ExchangeException),
            before_sleep=before_sleep_log(_log, logging.WARNING)
        ):
            with attempt:
                # We use a swap batch in order to swap the batch right before storing. With a
                # single batch, it may happen that our program gets cancelled at an `await`
                # point before we're able to clear the batch. This can cause same data to be
                # stored twice, raising an integrity error.
                batch = []
                swap_batch: list[Candle] = []
                current = floor_multiple(self._get_time_ms(), interval)

                try:
                    async for candle in self._stream_exchange_candles(
                        exchange=exchange,
                        symbol=symbol,
                        interval=interval,
                        start=start,
                        end=end,
                        current=current,
                        timeout=exchange_timeout,
                    ):
                        if candle.closed:
                            batch.append(candle)
                            if len(batch) == self._storage_batch_size:
                                del swap_batch[:]
                                batch_start = start
                                batch_end = batch[-1].time + interval
                                start = batch_end
                                swap_batch, batch = batch, swap_batch
                                await self._storage.store_time_series_and_span(
                                    shard=shard,
                                    key=CANDLE_KEY,
                                    items=swap_batch,
                                    start=batch_start,
                                    end=batch_end,
                                )
                        yield candle
                except (asyncio.CancelledError, ExchangeException):
                    if len(batch) > 0:
                        batch_start = start
                        batch_end = batch[-1].time + interval
                        start = batch_end
                        await self._storage.store_time_series_and_span(
                            shard=shard,
                            key=CANDLE_KEY,
                            items=batch,
                            start=batch_start,
                            end=batch_end,
                        )
                    raise
                else:
                    current = floor_multiple(self._get_time_ms(), interval)
                    await self._storage.store_time_series_and_span(
                        shard=shard,
                        key=CANDLE_KEY,
                        items=batch,
                        start=start,
                        end=min(current, end),
                    )

    async def _stream_exchange_candles(
        self, exchange: str, symbol: str, interval: int, start: int, end: int, current: int,
        timeout: Optional[float]
    ) -> AsyncIterable[Candle]:
        exchange_instance = self._exchanges[exchange]
        is_candle_interval_supported = interval in exchange_instance.list_candle_intervals()

        async def inner(stream: Optional[AsyncIterable[Candle]]) -> AsyncIterable[Candle]:
            if start < current:  # Historical.
                historical_end = min(end, current)
                if (
                    exchange_instance.can_stream_historical_candles
                    and is_candle_interval_supported
                ):
                    async for candle in exchange_instance.stream_historical_candles(
                        symbol, interval, start, historical_end
                    ):
                        yield candle
                else:
                    async for candle in self._stream_construct_candles(
                        exchange, symbol, interval, start, historical_end
                    ):
                        yield candle
            if stream:  # Future.
                async for candle in stream:
                    # If we start the websocket connection while candle is closing, we can also
                    # receive the same candle from here that we already got from historical.
                    # Ignore such candles.
                    if candle.time < current:
                        continue

                    if candle.time >= end:
                        break

                    yield candle

                    if candle.closed and candle.time == end - interval:
                        break

        async with AsyncExitStack() as stack:
            stream = None
            if end > current:
                if exchange_instance.can_stream_candles and is_candle_interval_supported:
                    stream = await stack.enter_async_context(
                        exchange_instance.connect_stream_candles(symbol, interval)
                    )
                else:
                    stream = self._stream_construct_candles(
                        exchange, symbol, interval, current, end
                    )

            last_candle_time = -1
            async for candle in stream_with_timeout(
                inner(stream),
                timeout if timeout is None else timeout / 1000,
            ):
                if candle.time % interval != 0:
                    _log.warning(
                        f'candle with bad time {candle} for interval {strfinterval(interval)}; '
                        'trying to adjusting back in time or skip if volume zero'
                    )
                    adjusted_time = floor_multiple(candle.time, interval)
                    if last_candle_time == adjusted_time:
                        if candle.volume > 0:
                            raise RuntimeError(
                                f'Received {symbol} {strfinterval(interval)} candle {candle} with '
                                'a time that does not fall into the interval. Cannot adjust back '
                                'in time because time coincides with last candle time '
                                f'{strftimestamp(last_candle_time)}. Cannot skip because volume '
                                'not zero'
                            )
                        else:
                            continue
                    candle = Candle(
                        time=adjusted_time,
                        open=candle.open,
                        high=candle.high,
                        low=candle.low,
                        close=candle.close,
                        volume=candle.volume,
                        closed=candle.closed,
                    )

                yield candle
                last_candle_time = candle.time

    async def _stream_construct_candles(
        self, exchange: str, symbol: str, interval: int, start: int, end: int
    ) -> AsyncIterable[Candle]:
        if not self._trades:
            raise ValueError('Trades component not configured. Unable to construct candles')

        _log.info(f'constructing {exchange} {symbol} {interval} candles from trades')

        current = start
        next_ = current + interval
        open_ = Decimal('0.0')
        high = Decimal('0.0')
        low = Decimal(f'{sys.maxsize}.0')
        close = Decimal('0.0')
        volume = Decimal('0.0')
        is_first = True
        async for trade in self._trades.stream_trades(exchange, symbol, start, end):
            if trade.time >= next_:
                assert not is_first
                yield Candle(
                    time=current,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    closed=True
                )
                current = next_
                next_ = current + interval
                open_ = Decimal('0.0')
                high = Decimal('0.0')
                low = Decimal(f'{sys.maxsize}.0')
                close = Decimal('0.0')
                volume = Decimal('0.0')
                is_first = True

            if is_first:
                open_ = trade.price
                is_first = False
            high = max(high, trade.price)
            low = min(low, trade.price)
            close = trade.price
            volume += trade.size

        if not is_first:
            yield Candle(
                time=current,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                closed=True
            )

    async def _stream_construct_candles_by_volume(
        self, exchange: str, symbol: str, volume: Decimal, start: int, end: int
    ) -> AsyncIterable[Candle]:
        if not self._trades:
            raise ValueError('Trades component not configured. Unable to construct candles')

        base_asset, _ = unpack_assets(symbol)
        _log.info(f'constructing {exchange} {symbol} {volume}{base_asset} candles from trades')

        current_volume = Decimal('0.0')
        is_first = True
        async for trade in self._trades.stream_trades(exchange, symbol, start, end):
            if is_first:
                is_first = False
                time = trade.time
                open_ = trade.price
                high = trade.price
                low = trade.price
                close = trade.price
            else:
                high = max(high, trade.price)
                low = min(low, trade.price)
                close = trade.price

            current_volume += trade.size
            while current_volume > volume:
                yield Candle(
                    time=time,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    closed=True
                )
                current_volume -= volume
                time = trade.time
                open_ = trade.price
                high = trade.price
                low = trade.price
                close = trade.price

    async def get_first_candle(self, exchange: str, symbol: str, interval: int) -> Candle:
        shard = key(exchange, symbol, interval)
        candle = await self._storage.get(
            shard=shard,
            key=FIRST_CANDLE_KEY,
            type_=Candle,
        )
        if not candle:
            if self._exchanges[exchange].can_stream_historical_earliest_candle:
                candle = await first_async(self._exchanges[exchange].stream_historical_candles(
                    symbol=symbol, interval=interval, start=0, end=MAX_TIME_MS
                ))
            else:
                # TODO: It would be faster to try to search the first candle of highest interval
                # first. Then slowly move to more granular intervals until we find the requested
                # one. The search space is significantly smaller with such approach.
                candle = await self._find_first_candle_by_binary_search(exchange, symbol, interval)
            await self._storage.set(
                shard=shard,
                key=FIRST_CANDLE_KEY,
                item=candle,
            )
        assert candle
        return candle

    async def _find_first_candle_by_binary_search(
        self, exchange: str, symbol: str, interval: int
    ) -> Candle:
        _log.info(
            f'{exchange} does not support streaming earliest candle; finding by binary search'
        )

        # TODO: Does not handle missing candles, hence, may yield incorrect results!
        start = ceil_multiple(self._earliest_exchange_start, interval)
        end = floor_multiple(self._get_time_ms(), interval)
        final_end = end  # We need this to not go into the future. We will mutate `end`.
        while True:
            mid = start + floor_multiple(((end - start) // 2), interval)
            from_ = mid
            to = min(from_ + 2 * interval, final_end)
            candles = await self.list_candles(exchange, symbol, interval, from_, to)
            if len(candles) == 0:
                start = mid + interval
            elif (
                len(candles) == 1
                and to - from_ > interval  # Must not be last candle.
            ):
                return candles[0]
            else:
                end = mid

            if start >= end:
                break

        raise ValueError('First candle not found')

    async def get_last_candle(self, exchange: str, symbol: str, interval: int) -> Candle:
        now = self._get_time_ms()
        end = floor_multiple(now, interval)
        start = end - interval
        return await first_async(self._exchanges[exchange].stream_historical_candles(
            symbol=symbol, interval=interval, start=start, end=end
        ))

    async def map_symbol_interval_candles(
        self, exchange: str, symbols: Iterable[str], intervals: Iterable[int], start: int, end: int
    ) -> dict[tuple[str, int], list[Candle]]:
        symbols = set(symbols)
        intervals = set(intervals)
        candles = await asyncio.gather(
            *(self.list_candles(exchange, s, i, start, end)
              for s, i in itertools.product(symbols, intervals))
        )
        return {(s, i): c for (s, i), c in zip(itertools.product(symbols, intervals), candles)}
