"""Ultra Compact Serialisation Language"""

import base64
import datetime
import typing
import re

from . import _mapping


_BRACKETS = re.compile(r"([\[\]])")  # [ or ]
_SCOPED = re.compile(r"^\[(.*)\]$")  # [[foo[bar]]] --group1-> [foo[bar]]
_FENCED = re.compile(r"^\[*~(.*)~\]*$")  # [[[~foo]bar~]] --group1-> foo]bar
_DASH = re.compile(r"[~]*[-]")  # -, ~-, ~~~- etc


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


class _inject:
    def from_bool(obj: bool) -> str:
        return "true" if obj else "false"

    def from_int(obj: int) -> str:
        return str(obj)

    def from_float(obj: float) -> str:
        return str(obj)

    def from_complex(obj: complex) -> str:
        return str(obj).strip("()")

    def from_str(obj: str) -> str:
        return obj

    def from_bytes(obj: bytes) -> str:
        try:
            s = obj.decode("utf8")
        except UnicodeDecodeError:
            return base64.b85encode(obj).decode()
        else:
            return "utf8:" + s

    def from_date(obj: datetime.date) -> str:
        return obj.isoformat()

    def from_time(obj: datetime.time) -> str:
        return obj.isoformat()

    def from_datetime(obj: datetime.datetime) -> str:
        return obj.isoformat()

    def from_list(obj: list) -> str:
        if obj == [""]:
            return "[]"
        return ",".join(_cover(item, ",") for item in obj)

    def from_dict(obj: dict) -> str:
        return ",".join(
            _cover(k, "[,=]") + "=" + _cover(v, ",") for k, v in obj.items()
        )

    def from_optional(obj: str | None) -> str:
        if obj is None:
            return "-"
        elif _DASH.fullmatch(obj):
            return "~" + obj
        else:
            return obj

    def from_union(name: str, obj: str) -> str:
        return _cover(name, "\[") + _cover(obj, ".")


class _surject:
    def to_bool(obj: str) -> bool:
        return {"true": True, "yes": True, "false": False, "no": False}[obj]

    def to_int(obj: str) -> int:
        return int(obj)

    def to_float(obj: str) -> float:
        return float(obj)

    def to_complex(obj: str) -> complex:
        return complex(obj)

    def to_str(obj: str) -> str:
        return obj

    def to_bytes(obj: str) -> bytes:
        if ":" in obj:
            enc, s = obj.split(":")
            return s.encode(enc)
        return base64.b85decode(obj)

    def to_date(obj: str) -> datetime.date:
        return datetime.date.fromisoformat(obj)

    def to_time(obj: str) -> datetime.time:
        return datetime.time.fromisoformat(obj)

    def to_datetime(obj: str) -> datetime.datetime:
        return datetime.datetime.fromisoformat(obj)

    def to_list(obj: str) -> list[str]:
        return [_expose(item) for item in _split_exposed(obj, ",")]

    def to_dict(obj: str) -> dict[str, str]:
        d = {}
        for si in _split_exposed(obj, ","):
            pos = _find_exposed(si, "=")
            if pos == -1:
                raise ValueError(f"dictionary item {si!r} does not contain an '=' sign")
            d[_expose(si[:pos])] = _expose(si[pos + 1 :])
        return d

    def to_optional(obj: str) -> str | None:
        return None if obj == "-" else obj[1:] if _DASH.fullmatch(obj) else obj

    def to_union(obj: str) -> tuple[str, str]:
        pos = _find_exposed(obj, "[")
        if pos == -1:
            return obj, ""
        return _expose(obj[:pos]), _expose(obj[pos:])


def dump(f, obj, T):
    f.write(_mapping.mapping_for(T).lower(obj, _inject))
    f.flush()


def dumps(obj, T):
    return _mapping.mapping_for(T).lower(obj, _inject)


def load(f, T):
    return _mapping.mapping_for(T).unlower(f.read(), _surject)


def loads(s, T):
    return _mapping.mapping_for(T).unlower(s, _surject)
