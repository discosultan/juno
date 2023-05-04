import argparse
import asyncio
import csv
import logging
from decimal import Decimal
from pathlib import Path

from juno import Candle, Timestamp_
from juno.exchanges import kraken
from juno.storages import SQLite
from juno.storages.storage import Storage

parser = argparse.ArgumentParser()
parser.add_argument("--file", help="Path to file containing Kraken candle data.")
args = parser.parse_args()


async def main() -> None:
    filepath = Path(args.file)
    assert filepath.is_file()
    # Example filepath stem: "XBTUSD_1440"
    kraken_symbol, kraken_interval = filepath.stem.split("_")
    symbol = kraken._from_http_symbol(kraken_symbol)
    interval = int(kraken_interval) * 60 * 1000

    candles = []
    with open(filepath, "r", encoding="utf-8") as file:
        reader = csv.reader(file)
        for line in reader:
            candle = Candle(
                time=int(line[0]) * 1000,
                open=Decimal(line[1]),
                high=Decimal(line[2]),
                low=Decimal(line[3]),
                close=Decimal(line[4]),
                volume=Decimal(line[5]),
            )
            candles.append(candle)
    if len(candles) == 0:
        return

    start = candles[0].time
    end = candles[-1].time + interval
    logging.info(f"start to end {Timestamp_.format_span(start, end)}")

    sqlite = SQLite()
    await sqlite.store_time_series_and_span(
        shard=Storage.key("kraken", symbol, interval),
        key="candle",
        items=candles,
        start=start,
        end=end,
    )


asyncio.run(main())
