import argparse
import asyncio
import logging

from juno import Account, Asset, Balance
from juno.components import User
from juno.exchanges import Exchange

parser = argparse.ArgumentParser()
parser.add_argument("accounts", nargs="?", type=lambda a: a.split(","), default=None)
parser.add_argument("-e", "--exchange", default="binance")
parser.add_argument("--stream", action="store_true", default=False)
parser.add_argument("--empty", action="store_true", default=False)
args = parser.parse_args()


async def main() -> None:
    exchange = Exchange.from_env(args.exchange)
    user = User([exchange])
    async with exchange, user:
        accounts = args.accounts
        if accounts is None:
            accounts = ["spot", "margin", "isolated"] if exchange.can_margin_borrow else ["spot"]
        logging.info(f"fetching balances for accounts: {accounts}")

        await log_accounts(user, accounts)

        if args.stream:
            if "isolated" in accounts:
                raise ValueError("Cannot stream all isolated margin accounts")
            await asyncio.gather(*(stream_account(user, a) for a in accounts))


async def log_accounts(user: User, accounts: list[Account]) -> None:
    account_balances = await user.map_balances(
        exchange=args.exchange, accounts=accounts, significant=not args.empty
    )
    log_all_empty = True
    for account, account_balance in account_balances.items():
        if len(account_balance) > 0 or args.empty:
            log_all_empty = False
            logging.info(f"{args.exchange} {account} account")
            for asset, balance in account_balance.items():
                logging.info(f"{asset} - {balance}")
    if log_all_empty:
        logging.info("all accounts empty")


async def stream_account(user: User, account: Account) -> None:
    async with user.sync_wallet(exchange=args.exchange, account=account) as wallet:
        while True:
            await wallet.updated.wait()
            log(account, wallet.balances)


def log(account: Account, account_balances: dict[Asset, Balance]) -> None:
    logging.info(f"{args.exchange} {account} account")
    for asset, balance in account_balances.items():
        logging.info(f"{asset} - {balance}")


asyncio.run(main())
