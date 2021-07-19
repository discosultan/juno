import asyncio
from decimal import Decimal

from juno import Balance
from juno.asyncio import stream_queue
from juno.components import User


async def test_get_balance(mocker) -> None:
    balance = Balance(available=Decimal("1.0"), hold=Decimal("0.0"))

    exchange = mocker.patch("juno.exchanges.Exchange", autospec=True)
    exchange.map_balances.return_value = {"spot": {"btc": balance}}

    async with User(exchanges=[exchange]) as user:
        out_balance = await user.get_balance(exchange="magicmock", account="spot", asset="btc")

    assert out_balance == balance


async def test_map_all_significant_balances(mocker) -> None:
    exchange = mocker.patch("juno.exchanges.Exchange", autospec=True)
    exchange.map_balances.side_effect = [
        {
            "spot": {
                "eth": Balance(),
                "btc": Balance(available=Decimal("1.0")),
            },
        },
        {
            "eth-btc": {
                "eth": Balance(available=Decimal("1.0")),
                "btc": Balance(),
            },
        },
    ]

    async with User(exchanges=[exchange]) as user:
        balances = await user.map_balances(
            exchange="magicmock", accounts=["spot", "isolated"], significant=True
        )

    assert balances == {
        "spot": {"btc": Balance(available=Decimal("1.0"))},
        "eth-btc": {"eth": Balance(available=Decimal("1.0"))},
    }


async def test_map_all_isolated(mocker) -> None:
    exchange = mocker.patch("juno.exchanges.Exchange", autospec=True)
    exchange.map_balances.return_value = {
        "eth-btc": {
            "eth": Balance(available=Decimal("1.0")),
            "btc": Balance(available=Decimal("2.0")),
        },
        "ltc-btc": {
            "ltc": Balance(),
            "btc": Balance(),
        },
    }

    async with User(exchanges=[exchange]) as user:
        balances = await user.map_balances(exchange="magicmock", accounts=["eth-btc"])

    assert balances == {
        "eth-btc": {
            "eth": Balance(available=Decimal("1.0")),
            "btc": Balance(available=Decimal("2.0")),
        },
    }


async def test_concurrent_sync_should_not_ping_exchange_multiple_times(mocker) -> None:
    balances = {"btc": Balance(available=Decimal("1.0"))}

    exchange = mocker.patch("juno.exchanges.Exchange", autospec=True)
    exchange.map_balances.return_value = {"spot": balances}

    async with User(exchanges=[exchange]) as user:
        # First calls to exchange.
        async with user.sync_wallet("magicmock", "spot") as wallet1:
            async with user.sync_wallet("magicmock", "spot") as wallet2:
                assert wallet2.balances == balances
            assert wallet1.balances == balances

        # Second calls to exchange.
        async with user.sync_wallet("magicmock", "spot") as wallet:
            assert wallet.balances == balances

    assert exchange.map_balances.call_count == 2
    assert exchange.connect_stream_balances.call_count == 2


async def test_concurrent_sync_should_have_isolated_events(mocker) -> None:
    exchange = mocker.patch("juno.exchanges.Exchange", autospec=True)
    exchange.map_balances.return_value = {"spot": {}}
    balances: asyncio.Queue[dict[str, Balance]] = asyncio.Queue()
    exchange.connect_stream_balances.return_value.__aenter__.return_value = stream_queue(balances)

    async with User(exchanges=[exchange]) as user:
        ctx1 = user.sync_wallet("magicmock", "spot")
        ctx2 = user.sync_wallet("magicmock", "spot")
        wallet1, wallet2 = await asyncio.gather(ctx1.__aenter__(), ctx2.__aenter__())

        assert not wallet1.updated.is_set()
        assert not wallet2.updated.is_set()

        await balances.put({"btc": Balance(available=Decimal("1.0"))})
        await balances.join()

        assert wallet1.updated.is_set()
        assert wallet2.updated.is_set()

        await wallet1.updated.wait()
        assert wallet2.updated.is_set()

        await asyncio.gather(
            ctx1.__aexit__(None, None, None),
            ctx2.__aexit__(None, None, None),
        )
