import simplejson as json


def _default(obj):
    internal_dict = getattr(obj, '__dict__', None)
    if internal_dict is not None:
        return internal_dict
    raise TypeError(f'Object of type {type(obj).__name__} is not JSON serializable')


def dumps(obj, indent=None):
    return json.dumps(obj, indent=indent, use_decimal=True, default=_default)


def load(fp):
    return json.load(fp, use_decimal=True)


def loads(s):
    return json.loads(s, use_decimal=True)
