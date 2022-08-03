import argparse
import asyncio
from decimal import Decimal

from juno import custodians
from juno.components import User
from juno.exchanges import Exchange

parser = argparse.ArgumentParser()
parser.add_argument("custodian", nargs="?", default="savings")
parser.add_argument("asset", nargs="?", default="btc")
parser.add_argument("-e", "--exchange", default="binance")
parser.add_argument("-s", "--size", nargs="?", type=Decimal, default=None)
args = parser.parse_args()


def _build_custodian(user: User, custodian: str) -> custodians.Custodian:
    if custodian == "savings":
        return custodians.Savings(user)
    elif custodian == "spot":
        return custodians.Spot(user)
    elif custodian == "stub":
        return custodians.Stub()
    else:
        raise ValueError(f"Unknown custodian {custodian}")


async def main() -> None:
    exchange = Exchange.from_env(args.exchange)
    user = User([exchange])
    async with exchange, user:
        custodian = _build_custodian(user, args.custodian)
        amount = await custodian.request(args.exchange, args.asset, args.size)
        await custodian.acquire(args.exchange, args.asset, amount)
        await custodian.release(args.exchange, args.asset, amount)


asyncio.run(main())
