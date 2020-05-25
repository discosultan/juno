from juno import utils


def test_replace_secrets() -> None:
    input_ = {'foo': 'hello', 'secret_bar': 'world'}
    output = utils.replace_secrets(input_)

    assert all(k in output for k in input_.keys())
    assert output['foo'] == 'hello'
    assert output['secret_bar'] != input_['secret_bar']


def test_unpack_symbol() -> None:
    assert utils.unpack_symbol('eth-btc') == ('eth', 'btc')


def test_extract_public() -> None:
    class Foo:
        a: int = 1
        b: int = 2
        _c: int = 3

        @property
        def d(self) -> int:
            return 4

    foo = Foo()
    x = utils.extract_public(foo, exclude=['b'])

    assert x.a == 1
    assert not getattr(x, 'b', None)
    assert not getattr(x, 'c', None)
    assert x.d == 4
    utils.extract_public(foo, exclude=['b'])  # Ensure can be called twice.
