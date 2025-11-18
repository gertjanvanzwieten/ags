import json

from ._mapping import mapping_without_date as _map


_settings = dict(
    indent=2,
    ensure_ascii=False,
)


def dump(f, obj, T):
    json.dump(_map(T).lower(obj, ""), f, **_settings)
    f.write("\n")


def dumps(obj, T):
    return json.dumps(_map(T).lower(obj, ""), **_settings) + "\n"


def load(f, T):
    return _map(T).unlower(json.load(f), "")


def loads(s, T):
    return _map(T).unlower(json.loads(s), "")
