__version__ = "0.1"


def _get_backend_for(path):
    if path.endswith(".json"):
        from . import json as backend
    elif path.endswith(".yml"):
        from . import yaml as backend
    else:
        from . import error

        raise error.AGSError("unrecognized file format")
    return backend


def load(path, T):
    backend = _get_backend_for(path)
    with open(path, "r") as f:
        return backend.load(f, T)


def dump(path, obj, T):
    backend = _get_backend_for(path)
    with open(path, "w") as f:
        return backend.dump(f, obj, T)
