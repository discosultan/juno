# Adds the following capabilities to base JSON module:
# - Handles dumping classes by unwrapping their internal __dict__.

from collections.abc import MutableMapping, MutableSequence
from copy import deepcopy
from decimal import Decimal
from typing import IO, Any, Iterable, Optional

import simplejson as json


def _prepare_dump(obj: Any) -> Any:
    # Unwrap complex types to their dict representations.
    # Convert tuples to lists.

    if isinstance(obj, tuple):
        obj = list(obj)
    elif hasattr(obj, '__dict__'):
        obj = obj.__dict__

    stack = [obj]
    while stack:
        item = stack.pop()
        it: Iterable[Any]
        if isinstance(item, MutableMapping):  # Json object.
            it = item.items()
        elif isinstance(item, MutableSequence):  # Json array.
            it = enumerate(item)
        else:  # Scalar.
            continue

        for k, v in it:
            if isinstance(v, tuple):
                item[k] = list(v)
                stack.append(item[k])
            elif hasattr(v, '__dict__'):
                item[k] = v.__dict__
                stack.append(item[k])
            else:
                stack.append(v)

    return obj


def _isdecimalformat(val: str) -> bool:
    return val in ['Infinity', '-Infinity'] or val.replace('.', '', 1).isdigit()


def _prepare_load(obj: Any) -> Any:
    # Convert infinity to Decimal (originally float, even with use_decimal=True).

    if isinstance(obj, float):
        if obj == float('inf'):
            return Decimal('Infinity')
        elif obj == float('-inf'):
            return Decimal('-Infinity')

    stack = [obj]
    while stack:
        item = stack.pop()
        it: Iterable[Any]
        if isinstance(item, MutableMapping):  # Json object.
            it = item.items()
        elif isinstance(item, MutableSequence):  # Json array.
            it = enumerate(item)
        else:  # Scalar.
            continue

        for k, v in it:
            if isinstance(v, float):
                if v == float('inf'):
                    item[k] = Decimal('Infinity')
                elif v == float('-inf'):
                    item[k] = Decimal('-Infinity')
            else:
                stack.append(v)

    return obj


def dumps(obj: Any, indent: Optional[int] = None, use_decimal=True) -> str:
    # Make a deep copy so we don't accidentally mutate source obj.
    obj = deepcopy(obj)
    obj = _prepare_dump(obj)
    return json.dumps(obj, indent=indent, use_decimal=use_decimal)


def load(fp: IO, use_decimal: bool = True) -> Any:
    res = json.load(fp, use_decimal=use_decimal)
    res = _prepare_load(res)
    return res


def loads(s: str, use_decimal: bool = True) -> Any:
    res = json.loads(s, use_decimal=use_decimal)
    res = _prepare_load(res)
    return res
