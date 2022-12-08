from juno.primitives.symbol import Symbol_


def test_assets() -> None:
    assert Symbol_.assets("eth-btc") == ("eth", "btc")


def test_base_asset() -> None:
    assert Symbol_.base_asset("eth-btc") == "eth"


def test_quote_asset() -> None:
    assert Symbol_.quote_asset("eth-btc") == "btc"


def test_swap() -> None:
    assert Symbol_.swap("eth-btc") == "btc-eth"


def test_iter_assets() -> None:
    assert list(Symbol_.iter_assets(["eth-btc", "ltc-btc"])) == ["eth", "btc", "ltc", "btc"]
