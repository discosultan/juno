import inspect
import os
import re
import sys
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional, Set, cast

import simplejson as json
from dateutil.parser import isoparse  # type: ignore

from juno.time import UTC, datetime_timestamp_ms, strpinterval
from juno.typing import filter_member_args, get_input_type_hints
from juno.utils import ischild, map_module_types, recursive_iter


def load_from_env(env: Mapping[str, str] = os.environ, prefix: str = 'JUNO', separator: str = '__'
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


def init_type(type_: type, components: Dict[str, Any] = {}, config: Dict[str, Any] = {}) -> Any:
    kwargs = {}

    # TODO: make use of assignment expression in py 3.8
    for dep_name, dep_type in get_input_type_hints(type_.__init__).items():  # type: ignore
        dep = next((c for c in components.values() if type(c) is dep_type), None)
        if dep:
            value = dep
        elif inspect.isabstract(dep_type):
            concretes = [c for c in components.values() if ischild(type(c), dep_type)]
            if len(concretes) != 1:
                raise NotImplementedError()
            value = concretes[0]
        elif dep_name == 'config':
            value = config
        elif dep_name == 'components':
            value = components
        else:
            component_config = config.get(type_.__name__.lower(), {})
            value = component_config.get(dep_name)
            if not value:
                origin = getattr(dep_type, '__origin__', None)
                if origin is list:
                    dep_type = dep_type.__args__[0]  # type: ignore
                    value = [c for c in components.values() if ischild(type(c), dep_type)]
                elif origin:
                    raise NotImplementedError()
                else:
                    raise ValueError(f'Unable to resolve {dep_name}: {dep_type} input for {type_}')

        kwargs[dep_name] = value

    return type_(**kwargs)


def load_all_types(config: Dict[str, Any], type_: type) -> List[Any]:
    result = []
    name = type_.__name__.lower()
    module_types = map_module_types(sys.modules[type_.__module__])
    for name in list_names(config, name):
        type_ = module_types[name]
        if not inspect.isabstract(type_):
            result.append(load_type(config, type_))
    return result


def load_type(config: Dict[str, Any], type_: type) -> Any:
    name = type_.__name__.lower()
    if inspect.isabstract(type_):
        type_ = map_module_types(sys.modules[type_.__module__])[config[name]]
        name = type_.__name__.lower()
    return type_(filter_member_args(type_.__init__, config[name]))  # type: ignore
