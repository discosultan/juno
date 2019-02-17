from datetime import datetime, timezone
from decimal import Decimal
import os
import re
from typing import Any, Dict, Mapping

import simplejson as json

from juno.time import strpinterval, datetime_timestamp_ms


def load_from_env(env: Mapping[str, str] = os.environ) -> Dict[str, Any]:
    # TODO: Support lists.
    result: Dict[str, Any] = {}
    entries = ((k.split('__')[1:], v) for k, v in env.items() if k.startswith('JUNO__'))
    for keys, value in entries:
        k1 = keys[0].lower()
        if len(keys) == 1:
            result[k1] = value
        elif len(keys) == 2:
            k2 = keys[1].lower()
            result[k1] = result.get(k1) or {}
            result[k1][k2] = value
        else:
            raise NotImplementedError()
    return transform(result)


def load_from_json_file(file: str) -> Dict[str, Any]:
    with open(file, 'r') as f:
        return transform(json.load(f))


def transform(value: Any) -> Any:
    if isinstance(value, float):
        raise ValueError('Decimals should be specified as strings to keep accuracy!')
    elif isinstance(value, dict):
        return {k: transform(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [transform(v) for v in value]
    elif isinstance(value, str):
        if re.match(r'-?\d+\.\d+', value):  # Decimal
            return Decimal(value)
        elif re.match(r'\d+(s|m|h)', value):  # Interval
            return strpinterval(value)
        elif re.match(r'\d+-\d+-\d+', value):  # Timestamp
            return datetime_timestamp_ms(datetime.strptime(value, '%Y-%m-%d')
                                                 .replace(tzinfo=timezone.utc))
    return value
