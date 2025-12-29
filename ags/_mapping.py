import base64
import dataclasses
import datetime
import enum
import functools
import inspect
import typing


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


def mapping_for(T, with_date) -> Mapping:
    if T in (int, float, bool, str, type(None)):
        return Primitive(T)

    if typing.get_origin(T) == typing.Literal:
        return Literal(typing.get_args(T))

    if T is complex:
        return Complex()

    if T is bytes:
        return Bytes()

    if typing.get_origin(T) == typing.Union:
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
                    d[name] = option, mapping_for(option, with_date)
            return Union(d)
        else:
            T = options[0]
            for T2 in options[1:]:
                T = typing.Union[T, T2]
            return Optional(mapping_for(T, with_date))

    if typing.get_origin(T) is list:
        (item_type,) = typing.get_args(T)
        return List(mapping_for(item_type, with_date))

    if typing.get_origin(T) is tuple:
        item_types = typing.get_args(T)
        if len(item_types) == 2 and item_types[1] == ...:
            return UniformTuple(mapping_for(item_types[0], with_date))
        else:
            items = []
            for i, item_type in enumerate(item_types):
                with context(f"[{i}]"):
                    items.append(mapping_for(item_type, with_date))
            return Tuple(tuple(items))

    if typing.get_origin(T) is dict:
        key_type, value_type = typing.get_args(T)
        if key_type is str:
            return Dict(mapping_for(value_type, with_date))

    if dataclasses.is_dataclass(T):
        fields = {}
        for field in dataclasses.fields(T):
            with context(f".{field.name}"):
                fields[field.name] = mapping_for(field.type, with_date)
        return DataClass(T, fields)

    if T in (datetime.date, datetime.time, datetime.datetime):
        if with_date:
            return Primitive(T)
        return DateTime(T)

    if type(T) is type(enum.Enum):
        return Enum(T)

    if isinstance(T, inspect.Signature):
        mappings = {}
        for param in T.parameters.values():
            with context(f".{param.name}"):
                mappings[param.name] = mapping_for(param.annotation, with_date)
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
                return Reduce(T, mapping_for(annotation, with_date))

    raise ValueError(f"cannot find a mapping for type {T!r}")


@dataclasses.dataclass
class Primitive:
    T: typing.Any

    def lower(self, obj):
        assert_isinstance(obj, self.T)
        return obj

    def unlower(self, obj):
        assert_isinstance(obj, self.T)
        return obj


@dataclasses.dataclass
class Literal:
    options: tuple[typing.Any, ...]

    def lower(self, obj):
        assert_in(obj, self.options)
        return obj

    def unlower(self, obj):
        assert_in(obj, self.options)
        return obj


class Complex:
    def lower(self, obj):
        assert_isinstance(obj, complex)
        if not obj.imag:
            return obj.real
        return dict(real=obj.real, imag=obj.imag)

    def unlower(self, obj):
        assert_isinstance(obj, (float, dict))
        if isinstance(obj, float):
            return complex(obj)
        if len(obj) == 2 and all(
            isinstance(obj.get(s), (int, float)) for s in ("real", "imag")
        ):
            return complex(obj["real"], obj["imag"])
        raise mismatch(
            expect="numerical dictionary values 'real' and 'imag'", got=repr(obj)
        )


class Bytes:
    def lower(self, obj):
        assert_isinstance(obj, bytes)
        try:
            s = obj.decode("utf8")
        except UnicodeDecodeError:
            return base64.b85encode(obj).decode()
        else:
            return "utf8:" + s

    def unlower(self, obj):
        assert_isinstance(obj, str)
        if ":" in obj:
            enc, s = obj.split(":")
            return s.encode(enc)
        return base64.b85decode(obj)


@dataclasses.dataclass
class Optional:
    mapping: Mapping

    def lower(self, obj):
        if obj is None:
            return None
        return self.mapping.lower(obj)

    def unlower(self, obj):
        if obj is None:
            return None
        return self.mapping.unlower(obj)


@dataclasses.dataclass
class Union:
    options: dict[str, tuple[typing.Any, Mapping]]

    def lower(self, obj):
        for name, (T, mapping) in self.options.items():
            if type(obj) is T:
                with context(f"({name})"):
                    return {name: mapping.lower(obj)}
        raise mismatch(
            expect="one of " + ", ".join(self.options), got=type(obj).__name__
        )

    def unlower(self, obj):
        assert_isinstance(obj, dict)
        if len(obj) != 1:
            raise mismatch(expect="a single dictionary item", got=len(obj))
        ((k, v),) = obj.items()
        assert_in(k, self.options)
        T, mapping = self.options[k]
        with context(f"({k})"):
            return mapping.unlower(v)


@dataclasses.dataclass
class List:
    mapping: Mapping

    def lower(self, obj):
        assert_isinstance(obj, list)
        items = []
        for i, item in enumerate(obj):
            with context(f"[{i}]"):
                items.append(self.mapping.lower(item))
        return items

    def unlower(self, obj):
        assert_isinstance(obj, list)
        items = []
        for i, item in enumerate(obj):
            with context(f"[{i}]"):
                items.append(self.mapping.unlower(item))
        return items


@dataclasses.dataclass
class Tuple:
    mappings: tuple[Mapping, ...]

    def lower(self, obj):
        assert_isinstance(obj, tuple)
        if len(obj) != len(self.mappings):
            mismatch(expect=f"{len(self.mappings)} items", got=len(obj))
        items = []
        for i, (item, mapping) in enumerate(zip(obj, self.mappings)):
            with context(f"[{i}]"):
                items.append(mapping.lower(item))
        return items

    def unlower(self, obj):
        assert_isinstance(obj, list)
        if len(obj) != len(self.mappings):
            mismatch(expect=f"{len(self.mappings)} items", got=len(obj))
        items = []
        for i, (item, mapping) in enumerate(zip(obj, self.mappings)):
            with context(f"[{i}]"):
                items.append(mapping.unlower(item))
        return tuple(items)


@dataclasses.dataclass
class UniformTuple:
    mapping: Mapping

    def lower(self, obj):
        assert_isinstance(obj, tuple)
        items = []
        for i, item in enumerate(obj):
            with context(f"[{i}]"):
                items.append(self.mapping.lower(item))
        return items

    def unlower(self, obj):
        assert_isinstance(obj, list)
        items = []
        for i, item in enumerate(obj):
            with context(f"[{i}]"):
                items.append(self.mapping.unlower(item))
        return tuple(items)


@dataclasses.dataclass
class Dict:
    mapping: Mapping

    def lower(self, obj):
        assert_isinstance(obj, dict)
        d = {}
        for k, v in obj.items():
            with context(f"[{k}]"):
                d[k] = self.mapping.lower(v)
        return d

    def unlower(self, obj):
        assert_isinstance(obj, dict)
        d = {}
        for k, v in obj.items():
            with context(f"[{k}]"):
                d[k] = self.mapping.unlower(v)
        return d


@dataclasses.dataclass
class DataClass:
    cls: type
    fields: dict[str, typing.Any]

    def lower(self, obj):
        if not dataclasses.is_dataclass(obj) or isinstance(obj, type):
            mismatch(expect="a dataclass object", got=type(obj).__name__)
        d = {}
        for name, mapping in self.fields.items():
            with context(f".{name}"):
                d[name] = mapping.lower(getattr(obj, name))
        return d

    def unlower(self, obj):
        assert_isinstance(obj, dict)
        d = {}
        for name, mapping in self.fields.items():
            with context(f".{name}"):
                d[name] = mapping.unlower(obj[name])
        return self.cls(**d)


@dataclasses.dataclass
class DateTime:
    datetype: type

    def lower(self, obj):
        assert_isinstance(obj, self.datetype)
        return obj.isoformat()

    def unlower(self, obj):
        assert_isinstance(obj, str)
        return self.datetype.fromisoformat(obj)


@dataclasses.dataclass
class Enum:
    E: enum.Enum

    def lower(self, obj):
        assert_isinstance(obj, self.E)
        return obj.name

    def unlower(self, obj):
        assert_isinstance(obj, str)
        assert_in(obj, self.E.__members__)
        return getattr(self.E, obj)


@dataclasses.dataclass
class Signature:
    signature: typing.Any
    mappings: dict[str, Mapping]

    def lower(self, obj):
        assert_isinstance(obj, inspect.BoundArguments)
        d = {}
        for name, v in obj.arguments.items():
            with context(f".{name}"):
                d[name] = self.mappings[name].lower(v)
        return d

    def unlower(self, obj):
        assert_isinstance(obj, dict)
        d = {}
        for name in obj:
            with context(f".{name}"):
                d[name] = self.mappings[name].unlower(obj[name])
        return self.signature.bind(**d)


@dataclasses.dataclass
class Reduce:
    T: type
    mapping: Mapping

    def lower(self, obj):
        f, args = obj.__reduce__()
        if f is not self.T:
            raise ValueError(f"reduction returned function {f}, expected {self.T}")
        if len(args) != 1:
            raise ValueError(
                f"reduction returned a tuple of length {len(args)}, expected 1"
            )
        return self.mapping.lower(args[0])

    def unlower(self, obj):
        return self.T(self.mapping.unlower(obj))


mapping_with_date = functools.partial(mapping_for, with_date=True)
mapping_without_date = functools.partial(mapping_for, with_date=False)
