from juno import utils


def test_replace_secrets() -> None:
    input = {'foo': 'hello', 'secret_bar': 'world'}
    output = utils.replace_secrets(input)

    assert all(k in output for k in input.keys())
    assert output['foo'] == 'hello'
    assert output['secret_bar'] != input['secret_bar']


def test_unpack_symbol() -> None:
    assert utils.unpack_symbol('eth-btc') == ('eth', 'btc')


def test_tonamedtuple() -> None:
    class Foo:
        a: int = 1
        _b: int = 2

        @property
        def c(self) -> int:
            return 3

    foo = Foo()
    x = utils.tonamedtuple(foo)

    assert x.a == 1
    assert not getattr(x, 'b', None)
    assert x.c == 3
    utils.tonamedtuple(foo)  # Ensure can be called twice.
