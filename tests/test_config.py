from decimal import Decimal

from juno import config


def test_transform():
    input = {
        'name': 'foo',
        'timestamp': '2000-01-01T00:00:00+00:00',
        'interval': '1h',
        'long_interval': '1d',
        'decimal': '1.5',
        'list': [],
        'dict': {}
    }
    expected_output = {
        'name': 'foo',
        'timestamp': 946_684_800_000,
        'interval': 3_600_000,
        'long_interval': 86_400_000,
        'decimal': Decimal('1.5'),
        'list': [],
        'dict': {}
    }
    output = config.transform(input)
    assert output == expected_output


def test_load_from_env():
    input = {
        'JUNO__FOO__BAR': 'a',
        'JUNO__FOO__BAZ': 'b',
        'JUNO__QUX__0': 'c',
        'JUNO__QUX__1': 'd',
        'JUNO__QUUX__0__CORGE': 'e'
    }
    expected_output = {
        'foo': {
            'bar': 'a',
            'baz': 'b',
        },
        'qux': ['c', 'd'],
        'quux': [{
            'corge': 'e'
        }]
    }
    output = config.load_from_env(input)
    assert output == expected_output


def test_list_names():
    input = {
        'foo': {
            'bar': 'a'
        },
        'bars': ['b', 'c'],
        'baz': 'd',
        'qux': [{
            'bar': 'e'
        }],
    }
    expected_output = set(('a', 'b', 'c', 'e'))
    output = config.list_names(input, 'bar')
    assert output == expected_output
