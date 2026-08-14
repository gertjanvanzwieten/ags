"""YAML Ain’t Markup Language"""

try:
    from yaml12 import read_yaml, parse_yaml, format_yaml
except ImportError:
    raise RuntimeError(
        "The AGS YAML backend requires py-yaml12 to be installed. Try: pip install ags[yaml]."
    )

from . import _mapping
from .json import _inject, _surject


def dump(f, obj, T):
    f.write(format_yaml(_mapping.mapping_for(T).lower(obj, _inject)))
    f.write("\n")


def dumps(obj, T):
    return format_yaml(_mapping.mapping_for(T).lower(obj, _inject)) + "\n"


def load(f, T):
    return _mapping.mapping_for(T).unlower(read_yaml(f), _surject)


def loads(s, T):
    return _mapping.mapping_for(T).unlower(parse_yaml(s), _surject)
