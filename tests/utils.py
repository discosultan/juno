from os import path
from typing import Any, Dict

import simplejson as json


def full_path(rel_path: str) -> str:
    return path.join(path.dirname(__file__), *filter(None, rel_path.split('/')))


def load_json_file(rel_path: str) -> Dict[str, Any]:
    with open(full_path(rel_path)) as f:
        return json.load(f, use_decimal=True)
