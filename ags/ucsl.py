"""Ultra Compact Serialisation Language"""

import base64
import datetime
import typing
import re

from . import _mapping


_BRACKETS = re.compile(r"([\[\]])")  # [ or ]
_SCOPED = re.compile(r"^\[(.*)\]$")  # [[foo[bar]]] --group1-> [foo[bar]]
_FENCED = re.compile(r"^\[*~(.*)~\]*$")  # [[[~foo]bar~]] --group1-> foo]bar


def _find_exposed(s: str, sub: str, start: int = 0):
    while (pos := s.find(sub, start)) != -1:
        if s[:pos].count("[") == s[:pos].count("]"):
            return pos
        start = pos + len(sub)
    return -1


def _split_exposed(s: str, sep: str, maxsplit: int = -1) -> typing.List[str]:
    items = []
    if s:
        while (pos := _find_exposed(s, sep)) != -1:
            items.append(s[:pos])
            s = s[pos + len(sep) :]
        items.append(s)
    return items


def _balance(s: str, regex: str):
    # Return the number of brackets that need to be added to the left (`left`)
    # and right (`right`) to make `s` nonnegative and balanced, and with no
    # exposed substrings matching the regular expression.
    left = right = 0
    for part in _BRACKETS.split(s):
        if part == "[":
            right += 1
        elif part == "]":
            if right == 0:
                left += 1
            else:
                right -= 1
        elif right == 0 and re.search(regex, part):
            left += 1
            right += 1
    return left, right


def _cover(s: str, regex: str) -> str:
    left, right = _balance(s, regex)
    if (
        left != right
        or left >= 2
        or _FENCED.fullmatch(s)
        or left == 0
        and _SCOPED.fullmatch(s)
    ):
        s = "~" + s + "~"  # add fence
    return "[" * left + s + "]" * right


def _expose(s: str) -> str:
    if s.count("[") != s.count("]"):
        raise ValueError(r"string {s!r} is not balanced")
    m = _FENCED.fullmatch(s) or _SCOPED.fullmatch(s)
    return m.group(1) if m else s


def _inject(obj):
    if type(obj) is str:
        return obj
    elif type(obj) in (int, float):
        return str(obj)
    elif type(obj) is complex:
        return str(obj).strip("()")
    elif type(obj) is bool:
        return "true" if obj else "false"
    elif type(obj) in (datetime.date, datetime.time, datetime.datetime):
        return obj.isoformat()
    elif type(obj) is bytes:
        try:
            s = obj.decode("utf8")
        except UnicodeDecodeError:
            return base64.b85encode(obj).decode()
        else:
            return "utf8:" + s
    elif obj is None:
        return ""
    elif type(obj) is _mapping.UnionValue:
        return _cover(obj.name, "\[") + _cover(obj.value, ".")
    elif type(obj) is _mapping.OptionalValue:
        return "-" if obj.value is None else _cover(obj.value, "^-$")
    elif type(obj) is dict:
        return ",".join(
            _cover(k, "[,=]") + "=" + _cover(v, ",") for k, v in obj.items()
        )
    elif type(obj) is list:
        if obj == [""]:
            return "[]"
        return ",".join(_cover(item, ",") for item in obj)
    else:
        raise TypeError(f"unsupported type: {type(obj).__name__}")


def _surject(obj, T):
    if type(obj) is not str:
        raise ValueError(f"expected str, got {type(obj).__name__}")
    if T is str:
        return obj
    elif T in (int, float, complex):
        return T(obj)
    elif T is bool:
        return {"true": True, "yes": True, "false": False, "no": False}[obj]
    elif T in (datetime.date, datetime.time, datetime.datetime):
        return T.fromisoformat(obj)
    elif T is bytes:
        if ":" in obj:
            enc, s = obj.split(":")
            return s.encode(enc)
        return base64.b85decode(obj)
    elif T is type(None):
        if obj:
            raise ValueError(f"expected empty string, got {obj!r}")
        return None
    elif T is _mapping.UnionValue:
        pos = _find_exposed(obj, "[")
        if pos == -1:
            return obj, ""
        return _mapping.UnionValue(_expose(obj[:pos]), _expose(obj[pos:]))
    elif T is _mapping.OptionalValue:
        return _mapping.OptionalValue(None if obj == "-" else _expose(obj))
    elif T is dict:
        d = {}
        for si in _split_exposed(obj, ","):
            pos = _find_exposed(si, "=")
            if pos == -1:
                raise ValueError(f"dictionary item {si!r} does not contain an '=' sign")
            d[_expose(si[:pos])] = _expose(si[pos + 1 :])
        return d
    elif T is list:
        return [_expose(item) for item in _split_exposed(obj, ",")]
    else:
        raise TypeError(f"unsupported type: {T.__name__}")


def dump(f, obj, T):
    f.write(_mapping.mapping_for(T).lower(obj, _inject))
    f.flush()


def dumps(obj, T):
    return _mapping.mapping_for(T).lower(obj, _inject)


def load(f, T):
    return _mapping.mapping_for(T).unlower(f.read(), _surject)


def loads(s, T):
    return _mapping.mapping_for(T).unlower(s, _surject)
