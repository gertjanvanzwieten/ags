"""JavaScript Object Notation"""

import base64
import datetime
import json
import typing

from . import _mapping


class _inject:
    def from_bool(obj: bool) -> bool:
        return obj

    def from_int(obj: int) -> int:
        return obj

    def from_float(obj: float) -> float:
        return obj

    def from_complex(obj: complex) -> float | str:
        return str(obj).strip("()") if obj.imag else obj.real

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

    def from_list(obj: list) -> list:
        return obj

    def from_dict(obj: dict) -> dict:
        return obj

    def from_optional(obj: typing.Optional) -> typing.Optional:
        return obj

    def from_union(name: str, obj: typing.Any) -> dict[str, typing.Any]:
        return {name: obj}


class _surject:
    def to_bool(obj: bool) -> bool:
        return obj

    def to_int(obj: int) -> int:
        return obj

    def to_float(obj: float) -> float:
        return obj

    def to_complex(obj: float | str) -> complex:
        return complex(obj)

    def to_str(obj: str) -> str:
        return obj

    def to_bytes(obj: str) -> bytes:
        if type(obj) is not str:
            raise ValueError(f"expected str, got {type(obj).__name__}")
        if ":" in obj:
            enc, s = obj.split(":")
            return s.encode(enc)
        return base64.b85decode(obj)

    def to_date(obj: str) -> datetime.date:
        if type(obj) is not str:
            raise ValueError(f"expected str, got {type(obj).__name__}")
        return datetime.date.fromisoformat(obj)

    def to_time(obj: str) -> datetime.time:
        if type(obj) is not str:
            raise ValueError(f"expected str, got {type(obj).__name__}")
        return datetime.time.fromisoformat(obj)

    def to_datetime(obj: str) -> datetime.datetime:
        if type(obj) is not str:
            raise ValueError(f"expected str, got {type(obj).__name__}")
        return datetime.datetime.fromisoformat(obj)

    def to_list(obj: list) -> list:
        return obj

    def to_dict(obj: dict) -> dict:
        return obj

    def to_optional(obj: typing.Optional) -> typing.Optional:
        return obj

    def to_union(obj: dict[str, typing.Any]) -> tuple[str, typing.Any]:
        if type(obj) is not dict:
            raise ValueError(f"expected dict, got {type(obj).__name__}")
        if len(obj) != 1:
            raise ValueError(f"expected one dictionary item, got {len(obj)}")
        ((name, value),) = obj.items()
        return name, value


_dump_settings = dict(
    indent=2,
    ensure_ascii=False,
)


def dump(f, obj, T):
    json.dump(_mapping.mapping_for(T).lower(obj, _inject), f, **_dump_settings)
    f.write("\n")


def dumps(obj, T):
    return (
        json.dumps(_mapping.mapping_for(T).lower(obj, _inject), **_dump_settings) + "\n"
    )


def load(f, T):
    return _mapping.mapping_for(T).unlower(json.load(f), _surject)


def loads(s, T):
    return _mapping.mapping_for(T).unlower(json.loads(s), _surject)
