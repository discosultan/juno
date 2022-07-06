from juno import utils


def test_unpack_assets() -> None:
    assert utils.unpack_assets("eth-btc") == ("eth", "btc")
