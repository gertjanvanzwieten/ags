import yaml

from ._mapping import mapping_with_date as _map


_settings = dict(
    allow_unicode=True,
    sort_keys=False,
)


def dump(f, obj, T):
    yaml.safe_dump(_map(T).lower(obj, ""), f, **_settings)


def dumps(obj, T):
    return yaml.safe_dump(_map(T).lower(obj, ""), **_settings)


def load(f, T):
    return _map(T).unlower(yaml.safe_load(f), "")


def loads(s, T):
    return _map(T).unlower(yaml.safe_load(s), "")
