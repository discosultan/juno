import asyncio
import logging

from juno import exchanges
from juno.asyncio import resolved_future
from juno.components import Wallet
from juno.config import from_env, init_instance

EXCHANGE_TYPE = exchanges.Binance
ASSETS = ['btc', 'eth']
KEEP_STREAMING = False

exchange_name = EXCHANGE_TYPE.__name__.lower()


async def main() -> None:
    client = init_instance(EXCHANGE_TYPE, from_env())
    wallet = Wallet([client])
    async with client, wallet:
        await asyncio.gather(
            process_balances(wallet, False),
            process_balances(wallet, True) if client.can_margin_trade else resolved_future(None),
        )


async def process_balances(wallet: Wallet, margin: bool) -> None:
    log_balances(wallet, margin)
    if KEEP_STREAMING:
        while True:
            await wallet.get_updated_event(exchange=exchange_name, margin=margin).wait()
            log_balances(wallet, margin)


def log_balances(wallet: Wallet, margin: bool) -> None:
    logging.info(f'{"MARGIN" if margin else "SPOT"} ACCOUNT')
    for asset in ASSETS:
        logging.info(f'{asset} - {wallet.get_balance(exchange_name, asset, margin=margin)}')


asyncio.run(main())
