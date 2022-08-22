from decimal import Decimal
from typing import IO, Any, Optional, overload

import yaml


def _decimal_constructor(loader, node):
    value = loader.construct_scalar(node)
    return Decimal(value)


# Support loading Decimals from a yaml config file.
# The value must be prefixed with the `!decimal` tag.
# https://stackoverflow.com/a/47346704/1466456
yaml.add_constructor("!decimal", _decimal_constructor)


@overload
def dump(data: Any, indent: Optional[int] = None) -> Any:
    ...


@overload
def dump(data: Any, stream: IO, indent: Optional[int] = None) -> None:
    ...


def dump(data, stream=None, indent=None):
    return yaml.dump(data=data, stream=stream, indent=indent, Dumper=yaml.Dumper)


def load(stream: IO | str) -> Any:
    return yaml.load(stream=stream, Loader=yaml.Loader)


__all__ = [
    "dump",
    "load",
]
