import argparse
import asyncio
import logging
from decimal import Decimal

from juno import OrderType, Side
from juno.exchanges import Exchange

parser = argparse.ArgumentParser()
parser.add_argument("side", nargs="?", type=lambda s: Side[s.upper()])
parser.add_argument("symbol", nargs="?")
parser.add_argument("-e", "--exchange", default="binance")
parser.add_argument("-a", "--account", default="spot")
parser.add_argument("-p", "--price", type=Decimal, default=None)
parser.add_argument("-q", "--quote", type=Decimal, default=None)
parser.add_argument("-s", "--size", type=Decimal, default=None)
parser.add_argument(
    "-t",
    "--order-type",
    type=lambda t: OrderType[t.upper()],
    default=OrderType.LIMIT,
)
parser.add_argument("--leverage", type=int, default=None)
parser.add_argument(
    "--reduce-only",
    action="store_true",
    default=None,
)
args = parser.parse_args()


async def main() -> None:
    async with Exchange.from_env(args.exchange) as exchange:
        res = await exchange.place_order(
            account=args.account,
            symbol=args.symbol,
            side=args.side,
            type_=args.order_type,
            price=args.price,
            quote=args.quote,
            size=args.size,
            leverage=args.leverage,
            reduce_only=args.reduce_only,
        )
        logging.info(res)


asyncio.run(main())
