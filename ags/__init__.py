__version__ = "0.2.2"


def _get_backend_for(path):
    if path.endswith(".json"):
        from . import json as backend
    elif path.endswith(".yml"):
        from . import yaml as backend
    else:
        raise ValueError(f"unrecognized file format for path {path!r}")
    return backend


def load(path, T):
    backend = _get_backend_for(path)
    with open(path, "r") as f:
        return backend.load(f, T)


def dump(path, obj, T):
    backend = _get_backend_for(path)
    with open(path, "w") as f:
        return backend.dump(f, obj, T)
