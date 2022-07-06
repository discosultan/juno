import asyncio
import itertools
import logging

from asyncstdlib import list as list_async

from juno import Timestamp_
from juno.math import spans_overlap
from juno.storages import SQLite

SHARD = "binance_ada-btc_300000"
KEY = "candle"
VERSION = "41"


async def main() -> None:
    storage = SQLite(VERSION)
    spans = await list_async(storage.stream_time_series_spans(shard=SHARD, key=KEY))
    logging.info(f"found {len(spans)} spans")
    overlapping = 0
    for span1, span2 in itertools.combinations(spans, 2):
        if spans_overlap(span1, span2):
            logging.info("OVERLAPPING SPAN FOUND:")
            logging.info(f"{span1} & {span2}")
            logging.info(f"{Timestamp_.format_span(*span1)} & {Timestamp_.format_span(*span2)}")
            overlapping += 1
    if overlapping == 0:
        logging.info("none overlapping")


asyncio.run(main())
