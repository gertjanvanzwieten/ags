"""JavaScript Object Notation"""

import base64
import datetime
import json

from . import _mapping


class _Backend:
    def lower(obj):
        if type(obj) in (datetime.date, datetime.time, datetime.datetime):
            return obj.isoformat()
        elif type(obj) is complex:
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
        elif type(obj) in (bool, int, float, str, dict, list, type(None)):
            return obj
        else:
            raise TypeError(f"unsupported type: {type(obj).__name__}")

    def unlower(obj, T):
        if T in (datetime.date, datetime.time, datetime.datetime):
            if type(obj) is not str:
                raise ValueError(f"expected str, got {type(obj).__name__}")
            return T.fromisoformat(obj)
        elif T is complex:
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
        elif T in (bool, int, float, str, dict, list, type(None)):
            if type(obj) is not T:
                raise ValueError(f"expected {T.__name__}, got {type(obj).__name__}")
            return obj
        else:
            raise TypeError(f"unsupported type: {T.__name__}")


_dump_settings = dict(
    indent=2,
    ensure_ascii=False,
)


def dump(f, obj, T):
    json.dump(_mapping.mapping_for(T).lower(obj, _Backend), f, **_dump_settings)
    f.write("\n")


def dumps(obj, T):
    return (
        json.dumps(_mapping.mapping_for(T).lower(obj, _Backend), **_dump_settings)
        + "\n"
    )


def load(f, T):
    return _mapping.mapping_for(T).unlower(json.load(f), _Backend)


def loads(s, T):
    return _mapping.mapping_for(T).unlower(json.loads(s), _Backend)
