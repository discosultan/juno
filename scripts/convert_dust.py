import argparse
import asyncio
import logging

from juno.config import from_env, init_instance
from juno.exchanges import Binance

parser = argparse.ArgumentParser()
parser.add_argument('assets', nargs='?', type=lambda s: s.split(','), default=None)
args = parser.parse_args()

DUST_BTC_THRESHOLD = 0.001


async def main() -> None:
    async with init_instance(Binance, from_env()) as client:
        assets = args.assets
        if assets is None:
            balances, tickers = await asyncio.gather(
                client.map_balances(account='spot'),
                client.map_tickers(),
            )
            assets = [
                a for a, b in balances['spot'].items()
                if a != 'btc'
                and (s := f'{a}-btc') in tickers
                and b.hold == 0
                and b.available > 0
                and b.available * tickers[s].price < DUST_BTC_THRESHOLD
            ]
        if len(assets) > 0:
            logging.info(f'converting {assets}')
            await client.convert_dust(assets)
        else:
            logging.info('nothing to convert')

asyncio.run(main())
