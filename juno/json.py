from collections import MutableMapping, MutableSequence
from copy import deepcopy
from decimal import Decimal
from typing import Any, IO, Iterable, Optional

import simplejson as json


def _unwrap_complex(obj: Any) -> Any:
    obj_dict = getattr(obj, '__dict__', None)
    return obj if obj_dict is None else obj_dict


def _prepare_dump(obj: Any) -> Any:
    # Make a deep copy so we don't accidentally mutate source obj.
    # Unrap complex type into its dict representation.
    # Convert any nested decimal to string.

    obj = deepcopy(obj)
    obj = _unwrap_complex(obj)

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
            item[k] = _unwrap_complex(v)
            if isinstance(v, Decimal):
                item[k] = str(v)
            else:
                stack.append(v)

    return obj


def dumps(obj: Any, indent: Optional[int] = None) -> str:
    return json.dumps(_prepare_dump(obj), indent=indent, use_decimal=True)


def load(fp: IO) -> Any:
    return json.load(fp, use_decimal=True)


def loads(s: str) -> Any:
    return json.loads(s, use_decimal=True)
