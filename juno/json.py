from collections import MutableMapping, MutableSequence
from copy import deepcopy
from decimal import Decimal
from typing import IO, Any, Iterable, Optional

import simplejson as json

from juno.typing import isnamedtuple


def _unwrap_complex(obj: Any) -> Any:
    obj_dict = getattr(obj, '__dict__', None)
    return obj if obj_dict is None else obj_dict


def _prepare_dump(obj: Any) -> Any:
    # Unrap complex type into its dict representation.
    # Convert any nested decimal to string.

    obj = _unwrap_complex(obj)

    stack = [obj]
    while stack:
        item = stack.pop()
        it: Iterable[Any]
        if isinstance(item, MutableMapping):  # Json object.
            print('MUTABLE MAPPING')
            it = item.items()
        elif isinstance(item, MutableSequence):  # Json array.
            print('MUTABLE SEQ')
            it = enumerate(item)
        else:  # Scalar.
            continue

        for k, v in it:
            item[k] = _unwrap_complex(v)
            if isinstance(v, Decimal):
                item[k] = str(v)
            else:
                stack.append(v)

    return obj


def _prepare_load(obj: Any) -> Any:
    # Convert any decimal strings to decimals.

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
            if isinstance(v, str) and v.replace('.', '', 1).isdigit():
                item[k] = Decimal(v)
            else:
                stack.append(v)

    return obj


def dumps(obj: Any, indent: Optional[int] = None) -> str:
    # Make a deep copy so we don't accidentally mutate source obj.
    # print('tawawlfnhakfkauwhfkuawhfkuawhfku')
    # print(obj)
    # print(type(obj.close))
    obj = deepcopy(obj)
    obj = _prepare_dump(obj)
    # print('tawawlfnhakfkauwhfkuawhfkuawhfku')
    # print(obj)
    # print(type(obj.close))
    return json.dumps(obj, indent=indent, use_decimal=True)


def load(fp: IO) -> Any:
    res = json.load(fp, use_decimal=True)
    res = _prepare_load(res)
    return res


def loads(s: str) -> Any:
    res = json.loads(s, use_decimal=True)
    res = _prepare_load(res)
    return res
