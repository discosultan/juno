from juno import utils


def test_unpack_assets() -> None:
    assert utils.unpack_assets("eth-btc") == ("eth", "btc")


def test_extract_public() -> None:
    class Foo:
        a: int = 1
        b: int = 2
        _c: int = 3

        @property
        def d(self) -> int:
            return 4

    foo = Foo()
    x = utils.extract_public(foo, exclude=["b"])

    assert x.a == 1
    assert not getattr(x, "b", None)
    assert not getattr(x, "c", None)
    assert x.d == 4
    utils.extract_public(foo, exclude=["b"])  # Ensure can be called twice.
