from decimal import Decimal

from juno import config


def test_transform():
    input = {
        'name': 'foo',
        'timestamp': '2000-01-01',
        'interval': '1h',
        'decimal': '1.5',
        'list': [],
        'dict': {}
    }
    expected_output = {
        'name': 'foo',
        'timestamp': 946_684_800_000,
        'interval': 3_600_000,
        'decimal': Decimal('1.5'),
        'list': [],
        'dict': {}
    }
    output = config.transform(input)
    assert output == expected_output


def test_load_from_env():
    input = {
        'JUNO__FOO__BAR': 'a',
        'JUNO__FOO__BAZ': 'b'
    }
    expected_output = {
        'foo': {
            'bar': 'a',
            'baz': 'b'
        }
    }
    output = config.load_from_env(input)
    assert output == expected_output


def test_list_required_names():
    input = {
        'foo': {
            'bar': 'a'
        },
        'bars': ['b', 'c'],
        'baz': 'd',
        'qux': [
            {'bar': 'e'}
        ]
    }
    expected_output = set(('a', 'b', 'c', 'e'))
    output = config.list_required_names(input, 'bar')
    assert output == expected_output
