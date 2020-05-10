# Sets sensible defaults to simplejson functions.

from decimal import Decimal
from typing import IO, Any, Optional, Tuple

import simplejson as json


def dump(
    obj: Any,
    fp: IO,
    indent: Optional[int] = None,
    separators: Optional[Tuple[str, str]] = None,
) -> None:
    return json.dump(
        obj,
        fp,
        use_decimal=True,
        allow_nan=True,
        indent=indent,
        separators=separators,
    )


def dumps(
    obj: Any,
    indent: Optional[int] = None,
    separators: Optional[Tuple[str, str]] = None,
) -> str:
    return json.dumps(
        obj,
        use_decimal=True,
        allow_nan=True,
        indent=indent,
        separators=separators,
    )


def load(fp: IO) -> Any:
    return json.load(
        fp,
        use_decimal=True,
        parse_constant=Decimal,
    )


def loads(s: str) -> Any:
    return json.loads(
        s,
        use_decimal=True,
        parse_constant=Decimal,
    )
