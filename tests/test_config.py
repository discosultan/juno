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
