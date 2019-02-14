from datetime import datetime
from decimal import Decimal
import os
import re
from typing import Any, Dict

import simplejson as json

from juno.time import strpinterval, datetime_timestamp_ms


# def load_from_env() -> Dict[str, Any]:
#     os.environ


def load_from_json_file(file: str) -> Dict[str, Any]:
    with open(file, 'r') as f:
        return _transform(json.load(f))


def _transform(src: Dict[str, Any]) -> Dict[str, Any]:
    dst: Dict[str, Any] = {}
    for key, value in src.items():
        if isinstance(value, float):
            raise ValueError('Decimals should be specified as strings to keep accuracy!')
        elif isinstance(value, dict):
            dst[key] = _transform(value)
        elif isinstance(value, str):
            if re.match(r'-?\d+\.\d+', value):  # Decimal
                dst[key] = Decimal(value)
            elif re.match(r'\d+(s|m|h)', value):  # Interval
                dst[key] = strpinterval(value)
            elif re.match(r'\d+-\d+-\d+', value):  # Timestamp
                pass
                # dst[key] = datetime_timestamp_ms(datetime.strptime())
        else:
            dst[key] = value
    return dst
