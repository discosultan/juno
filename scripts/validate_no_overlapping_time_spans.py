import asyncio
import itertools
import logging

from juno.asyncio import list_async
from juno.math import spans_overlap
from juno.storages import SQLite
from juno.time import strfspan

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
            logging.info(f"{strfspan(*span1)} & {strfspan(*span2)}")
            overlapping += 1
    if overlapping == 0:
        logging.info("none overlapping")


asyncio.run(main())
