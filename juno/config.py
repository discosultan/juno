import inspect
import os
import re
import sys
from types import ModuleType
from typing import (
    Any, Dict, List, Mapping, Optional, Set, Type, TypeVar, cast, get_args, get_origin
)

from juno import Interval, Timestamp, json
from juno.time import strpinterval, strptimestamp
from juno.typing import get_input_type_hints, isnamedtuple, filter_member_args
from juno.utils import get_module_type, map_module_types, recursive_iter

T = TypeVar('T')


def config_from_env(
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


def config_from_json_file(file: str) -> Dict[str, Any]:
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
        if re.match(r'\d+(ms|s|m|h|d|w|M|y)', value):  # Interval
            return strpinterval(value)
        elif re.match(r'\d+-\d+-\d+', value):  # Timestamp
            return strptimestamp(value)
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


def init_module_instance(module: ModuleType, config: Dict[str, Any]) -> Any:
    type_ = get_module_type(module, config['type'])
    return init_instance(type_, config)


def init_instance(type_: Type[T], config: Dict[str, Any]) -> T:
    init_hints = get_input_type_hints(type_ if isnamedtuple(type_) else type_.__init__)
    new_config = {}
    for k, t in init_hints.items():
        config_val = config.get(k)
        if config_val is not None:
            new_config[k] = _transform_value(config_val, t)
    return type_(**new_config)  # type: ignore


def _transform_value(value: Any, type_: Any) -> Any:
    if type_ is Interval:
        return strpinterval(value)
    if type_ is Timestamp:
        return strptimestamp(value)

    origin = get_origin(type_)
    if origin:
        if origin is list:
            st, = get_args(type_)
            return [_transform_value(sv, st) for sv in value]
        elif origin is dict:
            skt, svt = get_args(type_)
            return {
                _transform_value(sk, skt): _transform_value(sv, svt) for sk, sv in value.items()
            }

    return value


def load_type(type_: type, config: Dict[str, Any]) -> Any:
    if not inspect.isabstract(type_):
        raise ValueError()
    module_type_map = _map_type_parent_module_types(type_)
    return module_type_map[config.get(type_.__name__.lower(), {})]


def _map_type_parent_module_types(type_: type) -> Dict[str, type]:
    module_name = type_.__module__
    parent_module_name = module_name[0:module_name.rfind('.')]
    return map_module_types(sys.modules[parent_module_name])
