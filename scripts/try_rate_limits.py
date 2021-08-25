import asyncio
from decimal import Decimal

from juno.components import User
from juno.config import from_env, init_instance
from juno.exchanges import Binance

PRODUCT_IDS = {
    "busd": "BUSD001",
    "btc": "BTC001",
    "eth": "ETH001",
    "ada": "ADA001",
    "dot": "DOT001",
}

MAX_AMOUNT = Decimal("999.999")


async def main() -> None:
    exchange: Binance = init_instance(Binance, from_env())
    user = User([exchange])
    async with exchange, user:
        # await test_purchase(exchange, user)
        # await test_redeem(exchange, user)
        # await test_products(exchange)
        # await test_transfer(exchange, user)
        # await test_borrow_repay(user)
        await test_listen_key(exchange)


async def test_purchase(exchange: Binance, user: User) -> None:
    balances = (await user.map_balances("binance", ["spot"]))["spot"]
    await asyncio.gather(
        *(
            exchange.purchase_savings_product(PRODUCT_IDS[a], balances[a].available)
            for a in PRODUCT_IDS.keys()
        )
    )


async def test_redeem(exchange: Binance, user: User) -> None:
    balances = (await user.map_balances("binance", ["spot"]))["spot"]
    await asyncio.gather(
        *(
            exchange.redeem_savings_product(PRODUCT_IDS[a], balances[f"ld{a}"].available)
            for a in PRODUCT_IDS.keys()
        )
    )


async def test_products(exchange: Binance) -> None:
    await asyncio.gather(*(exchange.map_savings_products() for _ in range(22)))


async def test_transfer(exchange: Binance, user: User) -> None:
    assets = [
        "btc",
        "eth",
        "dot",
        "ada",
    ]
    balances = await user.map_balances("binance", ["spot", "isolated"])
    await asyncio.gather(
        *(exchange.transfer(a, balances["spot"][a].available, "spot", f"{a}-busd") for a in assets)
    )
    # await asyncio.gather(
    #     *(
    #         exchange.transfer(a, balances[f"{a}-busd"][a].available, f"{a}-busd", "spot")
    #         for a in assets
    #     )
    # )


async def test_borrow_repay(user: User) -> None:
    assets = [
        "btc",
        "eth",
        "dot",
        "ada",
        "bnb",
    ]
    balances = await user.map_balances("binance", ["spot", "isolated"])

    async def borrow_repay(a: str) -> None:
        await user.borrow("binance", a, balances[f"{a}-busd"][a].available, f"{a}-busd")
        # await user.repay("binance", a, MAX_AMOUNT, f"{a}-busd")

    await asyncio.gather(*(borrow_repay(a) for a in assets))


async def test_listen_key(exchange: Binance) -> None:
    spot_stream = await exchange._get_user_data_stream("spot")
    contents = await asyncio.gather(*(spot_stream._create_listen_key() for _ in range(10)))
    listen_key = contents[0]["listenKey"]
    await asyncio.gather(*(spot_stream._update_listen_key(listen_key) for _ in range(10)))
    await spot_stream._delete_listen_key(listen_key)


asyncio.run(main())
