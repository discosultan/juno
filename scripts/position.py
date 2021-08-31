from __future__ import annotations

import argparse
import asyncio
import logging
from decimal import Decimal

from juno.brokers import Limit
from juno.components import Chandler, Informant, Orderbook, User
from juno.config import from_env, init_instance
from juno.custodians import Savings, Spot, Stub
from juno.exchanges import Binance
from juno.positioner import Positioner
from juno.storages import SQLite
from juno.trading import CloseReason, TradingMode

parser = argparse.ArgumentParser()
parser.add_argument("symbols", type=lambda s: s.split(","))
parser.add_argument("quote", type=Decimal)
parser.add_argument(
    "-s",
    "--short",
    action="store_true",
    default=False,
    help="if set, open short; otherwise long positions",
)
parser.add_argument("--cycles", type=int, default=1)
parser.add_argument("--custodian", default="spot", help="either savings, spot or stub")
parser.add_argument(
    "--sleep", type=float, default=0.0, help="seconds to sleep before closing positions"
)
args = parser.parse_args()


async def main() -> None:
    exchange = init_instance(Binance, from_env())
    storage = SQLite()
    informant = Informant(storage=storage, exchanges=[exchange])
    chandler = Chandler(storage=storage, exchanges=[exchange])
    user = User(exchanges=[exchange])
    orderbook = Orderbook(exchanges=[exchange])
    broker = Limit(informant=informant, orderbook=orderbook, user=user)
    positioner = Positioner(
        informant=informant,
        chandler=chandler,
        broker=broker,
        user=user,
        custodians=[Savings(user), Spot(user), Stub()],
    )
    async with exchange, informant, chandler, user, orderbook:
        for i in range(args.cycles):
            logging.info(f"cycle {i}")

            logging.info(
                f"opening {'short' if args.short else 'long'} position(s) for {args.symbols}"
            )
            positions = await positioner.open_positions(
                exchange="binance",
                custodian=args.custodian,
                mode=TradingMode.LIVE,
                entries=[(s, args.quote, args.short) for s in args.symbols],
            )

            if args.sleep > 0:
                logging.info(f"sleeping for {args.sleep} seconds")
                await asyncio.sleep(args.sleep)

            logging.info(
                f"closing {'short' if args.short else 'long'} position(s) for {args.symbols}"
            )
            await positioner.close_positions(
                custodian=args.custodian,
                mode=TradingMode.LIVE,
                entries=[(p, CloseReason.STRATEGY) for p in positions],
            )


asyncio.run(main())
