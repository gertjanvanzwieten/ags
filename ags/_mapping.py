import dataclasses
import datetime
import enum
import inspect
import typing
import types


PRIMITIVES = (
    bool,
    int,
    float,
    complex,
    str,
    bytes,
    datetime.date,
    datetime.time,
    datetime.datetime,
)


class context:
    def __init__(self, context):
        self.context = context

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_value and len(exc_value.args) == 1:
            (arg,) = exc_value.args
            if not isinstance(arg, ErrorContext):
                arg = ErrorContext(arg)
                exc_value.args = (arg,)
            arg.prepend(self.context)


class ErrorContext:
    def __init__(self, message):
        self.message = message
        self.context = ""

    def prepend(self, context):
        self.context = context + self.context

    def __str__(self):
        return f"in {self.context}: {self.message}"

    def __repr__(self):
        return f"in {self.context}: {self.message!r}"


def mismatch(expect, got):
    return ValueError(f"expects {expect}, got {got}")


def assert_isinstance(obj, types):
    if not isinstance(types, tuple):
        types = (types,)
    if not any(type(obj) is T for T in types):
        raise mismatch(
            expect=" or ".join(T.__name__ for T in types), got=type(obj).__name__
        )


def assert_in(obj, options):
    if obj not in options:
        raise mismatch(expect="one of " + ", ".join(map(repr, options)), got=repr(obj))


class Mapping(typing.Protocol):
    def lower(self, obj: typing.Any) -> typing.Any: ...

    def unlower(self, obj: typing.Any) -> typing.Any: ...


def mapping_for(T) -> Mapping:
    if T in PRIMITIVES:
        return Primitive(T)

    if typing.get_origin(T) == typing.Literal:
        options = typing.get_args(T)
        if all(type(option) in PRIMITIVES for option in options):
            return Literal(options)

    if typing.get_origin(T) in (typing.Union, types.UnionType):
        options = list(typing.get_args(T))
        try:
            options.remove(type(None))
        except ValueError:
            d = {}
            for option in options:
                if typing.get_origin(option) == typing.Annotated:
                    option, name = typing.get_args(option)
                    if not isinstance(name, str):
                        raise ValueError("invalid or unsupported annotation")
                else:
                    name = option.__name__
                with context(f"({option})"):
                    d[name] = option, mapping_for(option)
            return Union(d)
        else:
            T = options[0]
            for T2 in options[1:]:
                T = typing.Union[T, T2]
            return Optional(mapping_for(T))

    if typing.get_origin(T) is list:
        (item_type,) = typing.get_args(T)
        return List(mapping_for(item_type))

    if typing.get_origin(T) is tuple:
        item_types = typing.get_args(T)
        if len(item_types) == 2 and item_types[1] == ...:
            return UniformTuple(mapping_for(item_types[0]))
        else:
            items = []
            for i, item_type in enumerate(item_types):
                with context(f"[{i}]"):
                    items.append(mapping_for(item_type))
            return Tuple(tuple(items))

    if typing.get_origin(T) is dict:
        key_type, value_type = typing.get_args(T)
        if key_type is str:
            return Dict(mapping_for(key_type), mapping_for(value_type))

    if dataclasses.is_dataclass(T):
        fields = {}
        for field in dataclasses.fields(T):
            with context(f".{field.name}"):
                fields[field.name] = mapping_for(field.type)
        return DataClass(T, fields)

    if type(T) is type(enum.Enum):
        return Enum(T)

    if isinstance(T, inspect.Signature):
        mappings = {}
        for param in T.parameters.values():
            with context(f".{param.name}"):
                if param.annotation != param.empty:
                    param_type = param.annotation
                elif param.default != param.empty:
                    param_type = type(param.default)
                else:
                    raise TypeError(f"cannot establish type for parameter {param.name}")
                mappings[param.name] = mapping_for(param_type)
        return Signature(T, mappings)

    if hasattr(T, "__reduce__"):
        ret = inspect.signature(T.__reduce__).return_annotation
        if typing.get_origin(ret) is tuple and len(typing.get_args(ret)) == 2:
            f, args = typing.get_args(ret)
            if (
                typing.get_origin(f) is type
                and typing.get_args(f) == (typing.Self,)
                and typing.get_origin(args) is tuple
                and len(typing.get_args(args)) == 1
            ):
                (annotation,) = typing.get_args(args)
                return Reduce(T, mapping_for(annotation))

    raise ValueError(f"cannot find a mapping for type {T!r}")


@dataclasses.dataclass
class Primitive:
    T: typing.Any

    def lower(self, obj, backend):
        assert_isinstance(obj, self.T)
        return backend.lower(obj)

    def unlower(self, obj, backend):
        return backend.unlower(obj, self.T)


@dataclasses.dataclass
class Literal:
    options: tuple[typing.Any, ...]

    def lower(self, obj, backend):
        assert_in(obj, self.options)
        return backend.lower(obj)

    def unlower(self, obj, backend):
        for option in self.options:
            if obj == backend.lower(option):
                return option
        raise mismatch(
            expect="one of "
            + ", ".join(str(backend.lower(option)) for option in self.options),
            got=obj,
        )


class OptionalValue(typing.NamedTuple):
    value: typing.Any


@dataclasses.dataclass
class Optional:
    mapping: Mapping

    def lower(self, obj, backend):
        return backend.lower(
            OptionalValue(None if obj is None else self.mapping.lower(obj, backend))
        )

    def unlower(self, obj, backend):
        (value,) = backend.unlower(obj, OptionalValue)
        if value is None:
            return None
        return self.mapping.unlower(value, backend)


class UnionValue(typing.NamedTuple):
    name: str
    value: typing.Any


@dataclasses.dataclass
class Union:
    options: dict[str, tuple[typing.Any, Mapping]]

    def lower(self, obj, backend):
        for name, (T, mapping) in self.options.items():
            if type(obj) is T:
                with context(f"({name})"):
                    return backend.lower(UnionValue(name, mapping.lower(obj, backend)))
        raise mismatch(
            expect="one of " + ", ".join(self.options), got=type(obj).__name__
        )

    def unlower(self, obj, backend):
        name, value = backend.unlower(obj, UnionValue)
        assert_in(name, self.options)
        T, mapping = self.options[name]
        with context(f"({name})"):
            return mapping.unlower(value, backend)


@dataclasses.dataclass
class List:
    mapping: Mapping

    def lower(self, obj, backend):
        assert_isinstance(obj, list)
        items = []
        for i, item in enumerate(obj):
            with context(f"[{i}]"):
                items.append(self.mapping.lower(item, backend))
        return backend.lower(items)

    def unlower(self, obj, backend):
        lobj = backend.unlower(obj, list)
        items = []
        for i, item in enumerate(lobj):
            with context(f"[{i}]"):
                items.append(self.mapping.unlower(item, backend))
        return items


@dataclasses.dataclass
class Tuple:
    mappings: tuple[Mapping, ...]

    def lower(self, obj, backend):
        assert_isinstance(obj, tuple)
        if len(obj) != len(self.mappings):
            mismatch(expect=f"{len(self.mappings)} items", got=len(obj))
        items = []
        for i, (item, mapping) in enumerate(zip(obj, self.mappings)):
            with context(f"[{i}]"):
                items.append(mapping.lower(item, backend))
        return backend.lower(items)

    def unlower(self, obj, backend):
        lobj = backend.unlower(obj, list)
        if len(lobj) != len(self.mappings):
            mismatch(expect=f"{len(self.mappings)} items", got=len(lobj))
        items = []
        for i, (item, mapping) in enumerate(zip(lobj, self.mappings)):
            with context(f"[{i}]"):
                items.append(mapping.unlower(item, backend))
        return tuple(items)


@dataclasses.dataclass
class UniformTuple:
    mapping: Mapping

    def lower(self, obj, backend):
        assert_isinstance(obj, tuple)
        items = []
        for i, item in enumerate(obj):
            with context(f"[{i}]"):
                items.append(self.mapping.lower(item, backend))
        return backend.lower(items)

    def unlower(self, obj, backend):
        lobj = backend.unlower(obj, list)
        items = []
        for i, item in enumerate(lobj):
            with context(f"[{i}]"):
                items.append(self.mapping.unlower(item, backend))
        return tuple(items)


@dataclasses.dataclass
class Dict:
    key_mapping: Mapping
    val_mapping: Mapping

    def lower(self, obj, backend):
        assert_isinstance(obj, dict)
        d = {}
        for k, v in obj.items():
            with context(f"[{k}]"):
                d[self.key_mapping.lower(k, backend)] = self.val_mapping.lower(
                    v, backend
                )
        return backend.lower(d)

    def unlower(self, obj, backend):
        dobj = backend.unlower(obj, dict)
        d = {}
        for k, v in dobj.items():
            with context(f"[{k}]"):
                d[self.key_mapping.unlower(k, backend)] = self.val_mapping.unlower(
                    v, backend
                )
        return d


@dataclasses.dataclass
class DataClass:
    cls: type
    fields: dict[str, typing.Any]

    def lower(self, obj, backend):
        if not dataclasses.is_dataclass(obj) or isinstance(obj, type):
            mismatch(expect="a dataclass object", got=type(obj).__name__)
        d = {}
        for name, mapping in self.fields.items():
            with context(f".{name}"):
                d[name] = mapping.lower(getattr(obj, name), backend)
        return backend.lower(d)

    def unlower(self, obj, backend):
        dobj = backend.unlower(obj, dict)
        d = {}
        for name, mapping in self.fields.items():
            with context(f".{name}"):
                d[name] = mapping.unlower(dobj[name], backend)
        return self.cls(**d)


@dataclasses.dataclass
class Enum:
    E: enum.Enum

    def lower(self, obj, backend):
        assert_isinstance(obj, self.E)
        return backend.lower(obj.name)

    def unlower(self, obj, backend):
        name = backend.unlower(obj, str)
        assert_in(name, self.E.__members__)
        return getattr(self.E, name)


@dataclasses.dataclass
class Signature:
    signature: typing.Any
    mappings: dict[str, Mapping]

    def lower(self, obj, backend):
        assert_isinstance(obj, inspect.BoundArguments)
        d = {}
        for name, v in obj.arguments.items():
            with context(f".{name}"):
                d[name] = self.mappings[name].lower(v, backend)
        return backend.lower(d)

    def unlower(self, obj, backend):
        dobj = backend.unlower(obj, dict)
        d = {}
        for name in dobj:
            with context(f".{name}"):
                d[name] = self.mappings[name].unlower(dobj[name], backend)
        return self.signature.bind(**d)


@dataclasses.dataclass
class Reduce:
    T: type
    mapping: Mapping

    def lower(self, obj, backend):
        f, args = obj.__reduce__()
        if f is not self.T:
            raise ValueError(f"reduction returned function {f}, expected {self.T}")
        if len(args) != 1:
            raise ValueError(
                f"reduction returned a tuple of length {len(args)}, expected 1"
            )
        return self.mapping.lower(args[0], backend)

    def unlower(self, obj, backend):
        return self.T(self.mapping.unlower(obj, backend))
