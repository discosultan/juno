import inspect
import os
import re
import sys
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional, Set, cast

from dateutil.parser import isoparse  # type: ignore

import juno.json as json
from juno.time import UTC, datetime_timestamp_ms, strpinterval
from juno.typing import filter_member_args
from juno.utils import map_module_types, recursive_iter


def load_from_env(
    env: Mapping[str, str] = os.environ, prefix: str = 'JUNO', separator: str = '__'
) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    entries = ((k.split(separator)[1:], v) for k, v in env.items()
               if k.startswith(prefix + separator))
    for keys, value in entries:
        typed_keys = [int(k) if str.isdigit(k) else k.lower() for k in keys]
        target: Dict[Any, Any] = result
        for i in range(len(typed_keys)):
            k1 = typed_keys[i]
            k2 = typed_keys[i + 1] if i < len(typed_keys) - 1 else None
            if k2 is None:
                target[k1] = value
            else:
                if isinstance(k2, int):
                    target[k1] = _ensure_list(_get(target, k1), k2 + 1)
                else:
                    target[k1] = _ensure_dict(_get(target, k1))
                target = target[k1]
    return cast(Dict[str, Any], transform(result))


def load_from_json_file(file: str) -> Dict[str, Any]:
    with open(file, 'r') as f:
        return cast(Dict[str, Any], transform(json.load(f)))


def transform(value: Any) -> Any:
    if isinstance(value, float):
        raise ValueError('Decimals should be specified as strings to keep accuracy')
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
            # Naive is handled as UTC.
            dt = isoparse(value)
            if dt.tzinfo:
                dt = dt.astimezone(UTC)
            else:
                dt = dt.replace(tzinfo=UTC)
            return datetime_timestamp_ms(dt)
    return value


def list_names(config: Dict[str, Any], name: str) -> Set[str]:
    result = set()
    name_plural = name + 's'
    for keys, v in recursive_iter(config):
        if (keys[-1] == name) or (len(keys) >= 2 and keys[-2] == name_plural):
            result.add(v)
    return result


def _ensure_list(existing: Optional[List[Any]], length: int) -> List[Any]:
    if existing is None:
        return [None] * length
    if len(existing) < length:
        return existing + [None] * (length - len(existing))
    return existing


def _ensure_dict(existing: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if existing is None:
        return {}
    return existing


def _get(collection: Any, key: Any) -> Optional[Any]:
    if isinstance(collection, list):
        return collection[key]
    else:
        return collection.get(key)


def load_instances(type_: type, config: Dict[str, Any]) -> List[Any]:
    result = []
    name = type_.__name__.lower()
    module_types = _map_type_parent_module_types(type_)
    for name in list_names(config, name):
        type_ = module_types[name]
        if not inspect.isabstract(type_):
            result.append(load_instance(type_, config))
    return result


def load_instance(type_: type, config: Dict[str, Any]) -> Any:
    if inspect.isabstract(type_):
        type_ = load_type(type_, config)
    name = type_.__name__.lower()
    return type_(**filter_member_args(type_.__init__, config.get(name, {})))  # type: ignore


def load_type(type_: type, config: Dict[str, Any]) -> Any:
    if not inspect.isabstract(type_):
        raise ValueError()
    module_type_map = _map_type_parent_module_types(type_)
    return module_type_map[config[type_.__name__.lower()]]


def _map_type_parent_module_types(type_: type) -> Dict[str, type]:
    module_name = type_.__module__
    parent_module_name = module_name[0:module_name.rfind('.')]
    return map_module_types(sys.modules[parent_module_name])
