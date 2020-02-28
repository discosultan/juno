import inspect
from decimal import Decimal
from types import TracebackType
from typing import (
    Any, Dict, Iterable, List, Optional, Type, Union, get_args, get_origin, get_type_hints
)

ExcType = Optional[Type[BaseException]]
ExcValue = Optional[BaseException]
Traceback = Optional[TracebackType]

JSONValue = Union[str, int, float, bool, None, Dict[str, Any], List[Any]]
JSONType = Union[Dict[str, JSONValue], List[JSONValue]]


def get_input_type_hints(obj: Any) -> Dict[str, type]:
    return {n: t for n, t in get_type_hints(obj).items() if n != 'return'}


def get_name(type_: Any) -> str:
    return str(type_) if get_origin(type_) else type_.__name__


def get_root_origin(type_: Any) -> Optional[Type[Any]]:
    last_origin = None
    origin = type_
    while True:
        origin = get_origin(origin)
        if origin is None:
            break
        else:
            last_origin = origin
    return last_origin


def isnamedtuple(obj: Any) -> bool:
    # Note that '_fields' is present only if the tuple has at least 1 field.
    return (
        inspect.isclass(obj)
        and issubclass(obj, tuple)
        and bool(getattr(obj, '_fields', False))
    )


def isoptional(obj: Any) -> bool:
    return get_origin(obj) is Union and type(None) in get_args(obj)


def load_by_typing(value: Any, type_: Type[Any]) -> Any:
    origin = get_root_origin(type_) or type_

    # Needs to be a list because type_ can be non-hashable for lookup in a set.
    if origin in [bool, int, float, str, Decimal]:
        return value

    if origin is list:
        sub_type = get_args(type_)[0]
        for i, sub_value in enumerate(value):
            value[i] = load_by_typing(sub_value, sub_type)
        return value
    elif origin is tuple:
        sub_types = get_args(type_)
        for i, (sub_value, sub_type) in enumerate(zip(value, sub_types)):
            value[i] = load_by_typing(sub_value, sub_type)
        return value
    elif origin is dict:
        sub_type = get_args(type_)[1]
        for key, sub_value in value.items():
            value[key] = load_by_typing(sub_value, sub_type)
        return value
    elif isnamedtuple(type_):
        annotations = get_type_hints(type_)
        args = []
        for i, (_name, sub_type) in enumerate(annotations.items()):
            sub_value = value[i]
            args.append(load_by_typing(sub_value, sub_type))
        return type_(*args)
    else:  # Try constructing a regular class.
        annotations = get_input_type_hints(origin.__init__)
        kwargs = {}
        import logging
        logging.critical(get_origin(type_))
        logging.critical('wadljwDajlwjdilawdil')
        logging.critical(annotations)
        for name, sub_type in annotations.items():
            import logging
            logging.critical('wadljwDajlwjdilawdil')
            logging.critical(sub_type)
            if name in annotations:
                sub_value = value[name]
                kwargs[name] = load_by_typing(sub_value, sub_type)
        return type_(**kwargs)


def types_match(obj: Any, type_: Type[Any]):
    origin = get_origin(type_) or type_
    if not isinstance(obj, origin):
        return False

    if origin in [bool, int, float, str, Decimal]:
        return True

    if isinstance(obj, tuple):
        if origin:  # Not named tuple.
            return all(types_match(so, st) for so, st, in zip(obj, get_args(type_)))
        else:  # Named tuple.
            return all(types_match(so, st) for so, st in zip(obj, get_type_hints(type_).values()))
    elif isinstance(obj, dict):
        assert origin
        key_type, value_type = get_args(type_)
        return all(types_match(k, key_type) and types_match(v, value_type) for k, v in obj.items())
    elif isinstance(obj, list):
        assert origin
        subtype, = get_args(type_)
        return all(types_match(so, subtype) for so in obj)
    else:
        raise NotImplementedError(f'Type matching not implemented for {type_}')


def map_input_args(obj: Any, args: Iterable[Any]) -> Dict[str, Any]:
    return {k: v for k, v in zip(get_input_type_hints(obj).keys(), args)}
