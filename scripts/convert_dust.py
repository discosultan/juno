import argparse
import asyncio
import logging

from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument("assets", nargs="?", type=lambda s: s.split(","), default=None)
parser.add_argument("--test", action="store_true", default=False)
args = parser.parse_args()

DUST_BTC_THRESHOLD = 0.001


async def main() -> None:
    async with init_instance(Binance, from_env()) as exchange:
        assets = args.assets
        if assets is None:
            balances, tickers = await asyncio.gather(
                exchange.map_balances(account="spot"),
                exchange.map_tickers(),
            )
            assets = [
                a
                for a, b in balances["spot"].items()
                if a not in {"btc", "bnb"}
                and (s := f"{a}-btc") in tickers
                and b.hold == 0
                and b.available > 0
                and b.available * tickers[s].price < DUST_BTC_THRESHOLD
            ]
        if len(assets) > 0:
            logging.info(f"converting {assets}")
            if not args.test:
                await exchange.convert_dust(assets)
        else:
            logging.info("nothing to convert")


asyncio.run(main())
