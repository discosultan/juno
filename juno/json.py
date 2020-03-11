# Adds the following capabilities to base JSON module:
# - Handles dumping classes by unwrapping their internal __dict__.

from collections.abc import MutableMapping, MutableSequence
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import IO, Any, Iterable, Optional

import simplejson as json


def _prepare_dump(obj: Any, skip_private: bool) -> Any:
    # Unwrap complex types to their dict representations.
    # Convert tuples to lists.
    # Strip private members if requested.

    if isinstance(obj, tuple):
        obj = list(obj)
    elif not isinstance(obj, Enum) and hasattr(obj, '__dict__'):
        obj = asdict(obj) if is_dataclass(obj) else obj.__dict__

    stack = [obj]
    while stack:
        item = stack.pop()
        it: Iterable[Any]
        if isinstance(item, MutableMapping):  # Json object.
            if skip_private:
                for k in [k for k in item.keys() if k.startswith('_') and not k.startswith('__')]:
                    del item[k]
            it = item.items()
        elif isinstance(item, MutableSequence):  # Json array.
            it = enumerate(item)
        else:  # Scalar.
            continue

        for k, v in it:
            if isinstance(v, tuple):
                item[k] = list(v)
                stack.append(item[k])
            elif not isinstance(v, Enum) and hasattr(v, '__dict__'):
                item[k] = asdict(v) if is_dataclass(v) else v.__dict__
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


def dump(
    obj: Any,
    fp: IO,
    indent: Optional[int] = None,
    use_decimal: bool = True,
    skip_private: bool = False,
) -> None:
    # Make a deep copy so we don't accidentally mutate source obj.
    obj = deepcopy(obj)
    obj = _prepare_dump(obj, skip_private=skip_private)
    return json.dump(obj, fp, indent=indent, use_decimal=use_decimal)


def dumps(
    obj: Any,
    indent: Optional[int] = None,
    use_decimal: bool = True,
    skip_private: bool = False,
) -> str:
    obj = deepcopy(obj)
    obj = _prepare_dump(obj, skip_private=skip_private)
    return json.dumps(obj, indent=indent, use_decimal=use_decimal)


def load(fp: IO, use_decimal: bool = True) -> Any:
    res = json.load(fp, use_decimal=use_decimal)
    res = _prepare_load(res)
    return res


def loads(s: str, use_decimal: bool = True) -> Any:
    res = json.loads(s, use_decimal=use_decimal)
    res = _prepare_load(res)
    return res
