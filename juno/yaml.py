from decimal import Decimal

from yaml import BaseLoader, Loader, add_constructor, load


def _decimal_constructor(loader, node):
    value = loader.construct_scalar(node)
    return Decimal(value)


# Support loading Decimals from a yaml config file.
# The value must be prefixed with the `!decimal` tag.
# https://stackoverflow.com/a/47346704/1466456
add_constructor("!decimal", _decimal_constructor)


__all__ = [
    "BaseLoader",
    "Loader",
    "load",
]
