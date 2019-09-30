import simplejson as json


def _default(obj):
    import logging
    logging.critical(obj)
    return obj.__dict__


def dumps(obj, indent=None):
    return json.dumps(obj, indent=indent, use_decimal=True, default=_default)


def load(fp):
    return json.load(fp, use_decimal=True)


def loads(s):
    return json.loads(s, use_decimal=True)
