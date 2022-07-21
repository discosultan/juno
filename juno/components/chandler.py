from __future__ import annotations

import asyncio
import itertools
import logging
import math
import sys
from contextlib import AsyncExitStack, aclosing
from decimal import Decimal
from typing import AsyncGenerator, AsyncIterable, Callable, Iterable, Optional

from asyncstdlib import list as list_async
from tenacity import AsyncRetrying, before_sleep_log, retry_if_exception_type

from juno import (
    Candle,
    CandleMeta,
    ExchangeException,
    Interval,
    Interval_,
    Symbol,
    Symbol_,
    Timestamp,
    Timestamp_,
)
from juno.asyncio import aclose, first_async, stream_with_timeout
from juno.common import CandleType
from juno.contextlib import AsyncContextManager
from juno.exchanges import Exchange
from juno.itertools import generate_missing_spans
from juno.storages import Storage
from juno.tenacity import stop_after_attempt_with_reset, wait_none_then_exponential

from .trades import Trades

_log = logging.getLogger(__name__)

_CANDLE_KEY = Candle.__name__.lower()
_FIRST_CANDLE_KEY = f"first_{_CANDLE_KEY}"


class Chandler(AsyncContextManager):
    def __init__(
        self,
        storage: Storage,
        exchanges: list[Exchange],
        trades: Optional[Trades] = None,
        get_time_ms: Callable[[], int] = Timestamp_.now,
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

    async def stream_concurrent_candles(
        self,
        exchange: str,
        entries: list[CandleMeta],
        start: Timestamp,
        end: Timestamp = Timestamp_.MAX_TIME,
        exchange_timeout: Optional[float] = None,
    ) -> AsyncIterable[tuple[Candle, CandleMeta]]:
        unique_entries = set(entries)
        desc_sorted_entries = sorted(unique_entries, key=lambda e: e[1], reverse=True)
        future_streams = [
            (
                (symbol, interval, type_),
                aiter(
                    self.stream_candles_fill_missing_with_none(
                        exchange=exchange,
                        symbol=symbol,
                        interval=interval,
                        start=start,
                        end=end,
                        exchange_timeout=exchange_timeout,
                        type_=type_,
                    )
                ),
            )
            for symbol, interval, type_ in desc_sorted_entries
        ]

        # For example:
        # - with intervals 3 and 5, the greatest common interval would be 1.
        # - with intervals 5 and 10, the greatest common interval would be 5.
        greatest_common_interval = math.gcd(*(interval for _, interval, _ in unique_entries))

        next_ = Timestamp_.floor(start, greatest_common_interval)
        next_end = Timestamp_.floor(end, greatest_common_interval)
        while next_ < next_end:
            next_ += greatest_common_interval
            for (symbol, interval, type_), stream in future_streams:
                if Timestamp_.is_in_interval(next_, interval):
                    optional_candle = await anext(stream)
                    if optional_candle is not None:
                        yield optional_candle, (symbol, interval, type_)

        await asyncio.gather(*(aclose(stream) for _, stream in future_streams))

    async def stream_candles_fill_missing_with_none(
        self,
        exchange: str,
        symbol: Symbol,
        interval: Interval,
        start: Timestamp,
        end: Timestamp = Timestamp_.MAX_TIME,
        exchange_timeout: Optional[float] = None,
        type_: CandleType = "regular",
    ) -> AsyncIterable[Optional[Candle]]:
        start = Timestamp_.floor(start, interval)
        end = Timestamp_.floor(end, interval)
        last_candle: Optional[Candle] = None
        stream = self.stream_candles(
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            exchange_timeout=exchange_timeout,
            type_=type_,
        )
        try:
            async for candle in stream:
                if last_candle:
                    num_missed = (candle.time - last_candle.time) // interval - 1
                else:
                    num_missed = (candle.time - start) // interval
                if num_missed > 0:
                    _log.info(f"filling {num_missed} candle(s) with None")
                    for _ in range(num_missed):
                        yield None
                yield candle
                last_candle = candle
        finally:
            await aclose(stream)

        if last_candle:
            num_missed = (end - last_candle.time) // interval - 1
        else:
            num_missed = (end - start) // interval
        if num_missed > 0:
            _log.info(f"filling {num_missed} candle(s) with None")
            for _ in range(num_missed):
                yield None

    async def list_candles(
        self,
        exchange: str,
        symbol: Symbol,
        interval: Interval,
        start: Timestamp,
        end: Timestamp = Timestamp_.MAX_TIME,
        exchange_timeout: Optional[float] = None,
        type_: CandleType = "regular",
    ) -> list[Candle]:
        return await list_async(
            self.stream_candles(
                exchange,
                symbol,
                interval,
                start,
                end,
                exchange_timeout,
                type_,
            )
        )

    async def stream_candles(
        self,
        exchange: str,
        symbol: Symbol,
        interval: Interval,
        start: Timestamp,
        end: Timestamp = Timestamp_.MAX_TIME,
        exchange_timeout: Optional[float] = None,
        type_: CandleType = "regular",
    ) -> AsyncIterable[Candle]:
        """Tries to stream candles for the specified range from local storage. If candles don't
        exist, streams them from an exchange and stores to local storage."""
        start = Timestamp_.floor(start, interval)
        end = Timestamp_.floor(end, interval)

        if end <= start:
            return

        shard = Storage.key(exchange, symbol, interval)
        candle_msg = f"{exchange} {symbol} {Interval_.format(interval)} candle(s)"

        _log.info(f"checking for existing {candle_msg} in local storage")
        existing_spans = await list_async(
            self._storage.stream_time_series_spans(
                shard=shard,
                key=_CANDLE_KEY,
                start=start,
                end=end,
            )
        )
        missing_spans = list(generate_missing_spans(start, end, existing_spans))

        spans = [(a, b, True) for a, b in existing_spans] + [
            (a, b, False) for a, b in missing_spans
        ]
        spans.sort(key=lambda s: s[0])

        last_candle: Optional[Candle] = None
        for span_start, span_end, exist_locally in spans:
            period_msg = f"{Timestamp_.format_span(span_start, span_end)}"
            if exist_locally:
                _log.info(f"local {candle_msg} exist between {period_msg}")
                stream = self._storage.stream_time_series(
                    shard=shard,
                    key=_CANDLE_KEY,
                    type_=Candle,
                    start=span_start,
                    end=span_end,
                )
            else:
                _log.info(f"missing {candle_msg} between {period_msg}")
                stream = self._stream_and_store_exchange_candles(
                    exchange=exchange,
                    symbol=symbol,
                    interval=interval,
                    start=span_start,
                    end=span_end,
                    exchange_timeout=exchange_timeout,
                )
            try:
                async for candle in stream:
                    if not last_candle and (num_missed := (candle.time - start) // interval) > 0:
                        _log.warning(
                            f"missed {num_missed} {candle_msg} from the start "
                            f"{Timestamp_.format(start)}; current candle {candle}"
                        )

                    if (
                        last_candle
                        and (time_diff := candle.time - last_candle.time) >= interval * 2
                    ):
                        num_missed = time_diff // interval - 1
                        _log.warning(
                            f"missed {num_missed} {candle_msg}; last closed candle "
                            f"{last_candle}; current candle {candle}"
                        )
                    if type_ == "regular":
                        yield candle
                    elif type_ == "heikin-ashi":
                        if last_candle is not None and last_candle.time == candle.time - interval:
                            yield Candle.heikin_ashi(previous=last_candle, current=candle)
                    else:
                        raise ValueError(f"Invalid candle type: {type_}")
                    last_candle = candle
            finally:
                await aclose(stream)

        if last_candle and (time_diff := end - last_candle.time) >= interval * 2:
            num_missed = time_diff // interval - 1
            _log.warning(
                f"missed {num_missed} {candle_msg} from the end {Timestamp_.format(end)}; "
                f"current candle {last_candle}"
            )
        elif not last_candle:
            _log.warning(f"missed all {candle_msg} between {Timestamp_.format_span(start, end)}")

    async def _stream_and_store_exchange_candles(
        self,
        exchange: str,
        symbol: Symbol,
        interval: Interval,
        start: Timestamp,
        end: Timestamp,
        exchange_timeout: Optional[float],
    ) -> AsyncGenerator[Candle, None]:
        shard = Storage.key(exchange, symbol, interval)
        # Note that we need to use a context manager based retrying because retry decorators do not
        # work with async generator functions.
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt_with_reset(8, 300),
            wait=wait_none_then_exponential(),
            retry=retry_if_exception_type(ExchangeException),
            before_sleep=before_sleep_log(_log, logging.WARNING),
        ):
            with attempt:
                # We use a swap batch in order to swap the batch right before storing. With a
                # single batch, it may happen that our program gets cancelled at an `await`
                # point before we're able to clear the batch. This can cause same data to be
                # stored twice, raising an integrity error.
                batch = []
                swap_batch: list[Candle] = []
                current = Timestamp_.floor(self._get_time_ms(), interval)

                try:
                    async with aclosing(
                        self._stream_exchange_candles(
                            exchange=exchange,
                            symbol=symbol,
                            interval=interval,
                            start=start,
                            end=end,
                            current=current,
                            timeout=exchange_timeout,
                        )
                    ) as stream:
                        async for candle in stream:
                            batch.append(candle)
                            if len(batch) == self._storage_batch_size:
                                del swap_batch[:]
                                batch_start = start
                                batch_end = batch[-1].time + interval
                                start = batch_end
                                swap_batch, batch = batch, swap_batch
                                await self._storage.store_time_series_and_span(
                                    shard=shard,
                                    key=_CANDLE_KEY,
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
                            key=_CANDLE_KEY,
                            items=batch,
                            start=batch_start,
                            end=batch_end,
                        )
                    raise
                else:
                    current = Timestamp_.floor(self._get_time_ms(), interval)
                    await self._storage.store_time_series_and_span(
                        shard=shard,
                        key=_CANDLE_KEY,
                        items=batch,
                        start=start,
                        end=min(current, end),
                    )

    async def _stream_exchange_candles(
        self,
        exchange: str,
        symbol: Symbol,
        interval: Interval,
        start: Timestamp,
        end: Timestamp,
        current: Timestamp,
        timeout: Optional[float],
    ) -> AsyncGenerator[Candle, None]:
        exchange_instance = self._exchanges[exchange]
        intervals = exchange_instance.list_candle_intervals()
        is_candle_interval_supported = interval in intervals

        async def inner(stream: Optional[AsyncIterable[Candle]]) -> AsyncIterable[Candle]:
            if start < current:  # Historical.
                historical_end = min(end, current)
                if (
                    exchange_instance.can_stream_historical_candles
                    and is_candle_interval_supported
                ):
                    historical_stream = exchange_instance.stream_historical_candles(
                        symbol=symbol,
                        interval=interval,
                        start=start,
                        end=historical_end,
                    )
                else:
                    historical_stream = self._stream_construct_candles(
                        exchange, symbol, interval, start, historical_end
                    )
                try:
                    async for candle in historical_stream:
                        yield candle
                finally:
                    await aclose(historical_stream)
            if stream:  # Future.
                try:
                    async for candle in stream:
                        # If we start the websocket connection while candle is closing, we can also
                        # receive the same candle from here that we already got from historical.
                        # Ignore such candles.
                        if candle.time < current:
                            continue

                        if candle.time >= end:
                            break

                        yield candle

                        if candle.time == end - interval:
                            break
                finally:
                    await aclose(stream)

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
            outer_stream = stream_with_timeout(
                inner(stream),
                None if timeout is None else timeout / 1000,
            )
            try:
                async for candle in outer_stream:
                    if interval < Interval_.WEEK and (candle.time % interval) != 0:
                        adjusted_time = Timestamp_.floor(candle.time, interval)
                        _log.warning(
                            f"candle with bad time {candle} for interval "
                            f"{Interval_.format(interval)}; trying to adjust back in time to "
                            f"{Timestamp_.format(adjusted_time)} or skip if volume zero"
                        )
                        if last_candle_time == adjusted_time:
                            if candle.volume > 0:
                                raise RuntimeError(
                                    f"Received {symbol} {Interval_.format(interval)} candle "
                                    f"{candle} with a time that does not fall into the interval. "
                                    "Cannot adjust back in time because time coincides with last "
                                    f"candle time {Timestamp_.format(last_candle_time)}. Cannot "
                                    "skip because volume not zero"
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
                        )

                    yield candle
                    last_candle_time = candle.time
            finally:
                await aclose(outer_stream)

    async def _stream_construct_candles(
        self, exchange: str, symbol: Symbol, interval: Interval, start: Timestamp, end: Timestamp
    ) -> AsyncGenerator[Candle, None]:
        if not self._trades:
            raise ValueError("Trades component not configured. Unable to construct candles")

        _log.info(f"constructing {exchange} {symbol} {interval} candles from trades")

        current = start
        next_ = current + interval
        open_ = Decimal("0.0")
        high = Decimal("0.0")
        low = Decimal(f"{sys.maxsize}.0")
        close = Decimal("0.0")
        volume = Decimal("0.0")
        is_first = True
        async for trade in self._trades.stream_trades(
            exchange=exchange, symbol=symbol, start=start, end=end
        ):
            if trade.time >= next_:
                assert not is_first
                yield Candle(
                    time=current,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                )
                current = next_
                next_ = current + interval
                open_ = Decimal("0.0")
                high = Decimal("0.0")
                low = Decimal(f"{sys.maxsize}.0")
                close = Decimal("0.0")
                volume = Decimal("0.0")
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
            )

    async def _stream_construct_candles_by_volume(
        self, exchange: str, symbol: Symbol, volume: Decimal, start: Timestamp, end: Timestamp
    ) -> AsyncGenerator[Candle, None]:
        if not self._trades:
            raise ValueError("Trades component not configured. Unable to construct candles")

        base_asset = Symbol_.base_asset(symbol)
        _log.info(f"constructing {exchange} {symbol} {volume}{base_asset} candles from trades")

        current_volume = Decimal("0.0")
        is_first = True
        async for trade in self._trades.stream_trades(
            exchange=exchange,
            symbol=symbol,
            start=start,
            end=end,
        ):
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
                )
                current_volume -= volume
                time = trade.time
                open_ = trade.price
                high = trade.price
                low = trade.price
                close = trade.price

    async def get_first_candle(self, exchange: str, symbol: Symbol, interval: Interval) -> Candle:
        shard = Storage.key(exchange, symbol, interval)
        candle = await self._storage.get(
            shard=shard,
            key=_FIRST_CANDLE_KEY,
            type_=Candle,
        )
        if not candle:
            exchange_instance = self._exchanges[exchange]
            if exchange_instance.can_stream_historical_earliest_candle:
                candle = await first_async(
                    self.stream_candles(
                        exchange=exchange,
                        symbol=symbol,
                        interval=interval,
                        start=0,
                        end=Timestamp_.MAX_TIME,
                    )
                )
            else:
                # TODO: It would be faster to try to search the first candle of highest interval
                # first. Then slowly move to more granular intervals until we find the requested
                # one. The search space is significantly smaller with such approach.
                candle = await self._find_first_candle_by_binary_search(
                    exchange=exchange,
                    symbol=symbol,
                    interval=interval,
                )
            await self._storage.set(
                shard=shard,
                key=_FIRST_CANDLE_KEY,
                item=candle,
            )
        assert candle
        return candle

    async def _find_first_candle_by_binary_search(
        self,
        exchange: str,
        symbol: Symbol,
        interval: Interval,
    ) -> Candle:
        _log.info(
            f"{exchange} does not support streaming earliest candle; finding by binary search"
        )

        # TODO: Does not handle missing candles, hence, may yield incorrect results!
        start = Timestamp_.ceil(self._earliest_exchange_start, interval)
        end = Timestamp_.floor(self._get_time_ms(), interval)
        final_end = end  # We need this to not go into the future. We will mutate `end`.
        while True:
            mid = start + Timestamp_.floor(((end - start) // 2), interval)
            from_ = mid
            to = min(from_ + 2 * interval, final_end)
            candles = await self.list_candles(exchange, symbol, interval, from_, to)
            if len(candles) == 0:
                start = mid + interval
            elif len(candles) == 1 and to - from_ > interval:  # Must not be last candle.
                return candles[0]
            else:
                end = mid

            if start >= end:
                break

        raise ValueError("First candle not found")

    async def get_last_candle(self, exchange: str, symbol: Symbol, interval: Interval) -> Candle:
        now = self._get_time_ms()
        end = Timestamp_.floor(now, interval)
        start = end - interval
        return await first_async(
            self.stream_candles(
                exchange=exchange,
                symbol=symbol,
                interval=interval,
                start=start,
                end=end,
            )
        )

    async def map_symbol_interval_candles(
        self,
        exchange: str,
        symbols: Iterable[str],
        intervals: Iterable[int],
        start: Timestamp,
        end: Timestamp,
    ) -> dict[tuple[str, int], list[Candle]]:
        symbols = set(symbols)
        intervals = set(intervals)
        candles = await asyncio.gather(
            *(
                self.list_candles(exchange, s, i, start, end)
                for s, i in itertools.product(symbols, intervals)
            )
        )
        return {(s, i): c for (s, i), c in zip(itertools.product(symbols, intervals), candles)}

    def list_candle_intervals(
        self, exchange: str, patterns: Optional[list[int]] = None
    ) -> list[int]:
        intervals = self._exchanges[exchange].list_candle_intervals()
        if patterns is None:
            return intervals

        return [i for i in intervals if i in patterns]
