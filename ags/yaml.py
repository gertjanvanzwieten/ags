"""YAML Ain’t Markup Language"""

import base64
import datetime
import yaml

from . import _mapping


def _inject(obj):
    if type(obj) is complex:
        return str(obj).strip("()") if obj.imag else obj.real
    elif type(obj) is bytes:
        try:
            s = obj.decode("utf8")
        except UnicodeDecodeError:
            return base64.b85encode(obj).decode()
        else:
            return "utf8:" + s
    elif type(obj) is _mapping.UnionValue:
        return {obj.name: obj.value}
    elif type(obj) is _mapping.OptionalValue:
        return obj.value
    elif type(obj) in (
        bool,
        int,
        float,
        str,
        dict,
        list,
        type(None),
        datetime.date,
        datetime.time,
        datetime.datetime,
    ):
        return obj
    else:
        raise TypeError(f"unsupported type: {type(obj).__name__}")


def _surject(obj, T):
    if T is complex:
        return complex(obj)
    elif T is bytes:
        if type(obj) is not str:
            raise ValueError(f"expected str, got {type(obj).__name__}")
        if ":" in obj:
            enc, s = obj.split(":")
            return s.encode(enc)
        return base64.b85decode(obj)
    elif T is _mapping.UnionValue:
        if type(obj) is not dict:
            raise ValueError(f"expected dict, got {type(obj).__name__}")
        if len(obj) != 1:
            raise ValueError(f"expected one dictionary item, got {len(obj)}")
        ((name, value),) = obj.items()
        return _mapping.UnionValue(name, value)
    elif T is _mapping.OptionalValue:
        return _mapping.OptionalValue(obj)
    elif T in (
        bool,
        int,
        float,
        str,
        dict,
        list,
        type(None),
        datetime.date,
        datetime.time,
        datetime.datetime,
    ):
        if type(obj) is not T:
            raise ValueError(f"expected {T.__name__}, got {type(obj).__name__}")
        return obj
    else:
        raise TypeError(f"unsupported type: {T.__name__}")


_dump_settings = dict(
    allow_unicode=True,
    sort_keys=False,
)


def dump(f, obj, T):
    yaml.safe_dump(_mapping.mapping_for(T).lower(obj, _inject), f, **_dump_settings)


def dumps(obj, T):
    return yaml.safe_dump(_mapping.mapping_for(T).lower(obj, _inject), **_dump_settings)


def load(f, T):
    return _mapping.mapping_for(T).unlower(yaml.safe_load(f), _surject)


def loads(s, T):
    return _mapping.mapping_for(T).unlower(yaml.safe_load(s), _surject)
