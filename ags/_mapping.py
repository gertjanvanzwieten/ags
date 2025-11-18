import base64
import dataclasses
import datetime
import enum
import functools
import inspect
import typing

from .error import AGSError


def mismatch(context, expect, got):
    return AGSError(f"expects {expect}, got {got}", context)


def assert_isinstance(obj, types, context):
    if not isinstance(types, tuple):
        types = (types,)
    if not any(type(obj) is T for T in types):
        raise mismatch(
            context,
            expect=" or ".join(T.__name__ for T in types),
            got=type(obj).__name__,
        )


def assert_in(obj, options, context):
    if obj not in options:
        raise mismatch(
            context, expect="one of " + ", ".join(map(repr, options)), got=repr(obj)
        )


class Mapping(typing.Protocol):
    def lower(self, obj: typing.Any, context: str) -> typing.Any: ...

    def unlower(self, obj: typing.Any, context: str) -> typing.Any: ...


def mapping_for(T, context, with_date) -> Mapping:
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
                        raise AGSError("invalid or unsupported annotation", context)
                else:
                    name = option.__name__
                d[name] = option, mapping_for(option, f"{context}({option})", with_date)
            return Union(d)
        else:
            T = options[0]
            for T2 in options[1:]:
                T = typing.Union[T, T2]
            return Optional(mapping_for(T, context, with_date))

    if typing.get_origin(T) is list:
        (item_type,) = typing.get_args(T)
        return List(mapping_for(item_type, context, with_date))

    if typing.get_origin(T) is tuple:
        item_types = typing.get_args(T)
        if len(item_types) == 2 and item_types[1] == ...:
            return UniformTuple(mapping_for(item_types[0], context, with_date))
        else:
            return Tuple(
                tuple(
                    mapping_for(item_type, f"{context}[{i}]", with_date)
                    for i, item_type in enumerate(item_types)
                )
            )

    if typing.get_origin(T) is dict:
        key_type, value_type = typing.get_args(T)
        if key_type is str:
            return Dict(mapping_for(value_type, context, with_date))

    if dataclasses.is_dataclass(T):
        return DataClass(
            T,
            {
                field.name: mapping_for(
                    field.type, f"{context}.{field.name}", with_date
                )
                for field in dataclasses.fields(T)
            },
        )

    if T in (datetime.date, datetime.time, datetime.datetime):
        if with_date:
            return Primitive(T)
        return DateTime(T)

    if type(T) is type(enum.Enum):
        return Enum(T)

    if isinstance(T, inspect.Signature):
        return Signature(
            T,
            {
                param.name: mapping_for(
                    param.annotation, f"{context}.{param.name}", with_date
                )
                for param in T.parameters.values()
            },
        )

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
                return Reduce(T, mapping_for(annotation, context, with_date))

    raise AGSError(f"cannot find a mapping for type {T!r}", context)


@dataclasses.dataclass
class Primitive:
    T: typing.Any

    def lower(self, obj, context):
        assert_isinstance(obj, self.T, context)
        return obj

    def unlower(self, obj, context):
        assert_isinstance(obj, self.T, context)
        return obj


@dataclasses.dataclass
class Literal:
    options: tuple[typing.Any, ...]

    def lower(self, obj, context):
        assert_in(obj, self.options, context)
        return obj

    def unlower(self, obj, context):
        assert_in(obj, self.options, context)
        return obj


class Complex:
    def lower(self, obj, context):
        assert_isinstance(obj, complex, context)
        if not obj.imag:
            return obj.real
        return dict(real=obj.real, imag=obj.imag)

    def unlower(self, obj, context):
        assert_isinstance(obj, (float, dict), context)
        if isinstance(obj, float):
            return complex(obj)
        if len(obj) == 2 and all(
            isinstance(obj.get(s), (int, float)) for s in ("real", "imag")
        ):
            return complex(obj["real"], obj["imag"])
        raise mismatch(
            context,
            expect="numerical dictionary values 'real' and 'imag'",
            got=repr(obj),
        )


class Bytes:
    def lower(self, obj, context):
        assert_isinstance(obj, bytes, context)
        try:
            s = obj.decode("utf8")
        except UnicodeDecodeError:
            return base64.b85encode(obj).decode()
        else:
            return "utf8:" + s

    def unlower(self, obj, context):
        assert_isinstance(obj, str, context)
        if ':' in obj:
            enc, s = obj.split(':')
            return s.encode(enc)
        return base64.b85decode(obj)


@dataclasses.dataclass
class Optional:
    mapping: Mapping

    def lower(self, obj, context):
        if obj is None:
            return None
        return self.mapping.lower(obj, context)

    def unlower(self, obj, context):
        if obj is None:
            return None
        return self.mapping.unlower(obj, context)


@dataclasses.dataclass
class Union:
    options: dict[str, tuple[typing.Any, Mapping]]

    def lower(self, obj, context):
        for name, (T, mapping) in self.options.items():
            if type(obj) is T:
                return {name: mapping.lower(obj, f"{context}({name})")}
        raise mismatch(
            context, expect="one of " + ", ".join(self.mapping), got=type(obj).__name__
        )

    def unlower(self, obj, context):
        assert_isinstance(obj, dict, context)
        if len(obj) != 1:
            raise mismatch(context, expect="a single dictionary item", got=len(obj))
        ((k, v),) = obj.items()
        assert_in(k, self.options, context)
        T, mapping = self.options[k]
        return mapping.unlower(v, f"{context}({k})")


@dataclasses.dataclass
class List:
    mapping: Mapping

    def lower(self, obj, context):
        assert_isinstance(obj, list, context)
        return [
            self.mapping.lower(item, f"{context}[{i}]") for i, item in enumerate(obj)
        ]

    def unlower(self, obj, context):
        assert_isinstance(obj, list, context)
        return [
            self.mapping.unlower(item, f"{context}[{i}]") for i, item in enumerate(obj)
        ]


@dataclasses.dataclass
class Tuple:
    mappings: tuple[Mapping, ...]

    def lower(self, obj, context):
        assert_isinstance(obj, tuple, context)
        if len(obj) != len(self.mappings):
            mismatch(context, expect=f"{len(self.mappings)} items", got=len(obj))
        return [
            mapping.lower(item, f"{context}[{i}]")
            for i, (item, mapping) in enumerate(zip(obj, self.mappings))
        ]

    def unlower(self, obj, context):
        assert_isinstance(obj, list, context)
        if len(obj) != len(self.mappings):
            mismatch(context, expect=f"{len(self.mappings)} items", got=len(obj))
        return tuple(
            mapping.unlower(item, f"{context}[{i}]")
            for i, (item, mapping) in enumerate(zip(obj, self.mappings))
        )


@dataclasses.dataclass
class UniformTuple:
    mapping: Mapping

    def lower(self, obj, context):
        assert_isinstance(obj, tuple, context)
        return [
            self.mapping.lower(item, f"{context}[{i}]") for i, item in enumerate(obj)
        ]

    def unlower(self, obj, context):
        assert_isinstance(obj, list, context)
        return tuple(
            self.mapping.unlower(item, f"{context}[{i}]") for i, item in enumerate(obj)
        )


@dataclasses.dataclass
class Dict:
    mapping: Mapping

    def lower(self, obj, context):
        assert_isinstance(obj, dict, context)
        return {k: self.mapping.lower(v, f"{context}[{k}]") for k, v in obj.items()}

    def unlower(self, obj, context):
        assert_isinstance(obj, dict, context)
        return {k: self.mapping.unlower(v, f"{context}[{k}]") for k, v in obj.items()}


@dataclasses.dataclass
class DataClass:
    cls: type
    fields: dict[str, typing.Any]

    def lower(self, obj, context):
        if not dataclasses.is_dataclass(obj) or isinstance(obj, type):
            mismatch(context, expect="a dataclass object", got=type(obj).__name__)
        return {
            name: mapping.lower(getattr(obj, name), f"{context}.{name}")
            for name, mapping in self.fields.items()
        }

    def unlower(self, obj, context):
        assert_isinstance(obj, dict, context)
        return self.cls(
            **{
                name: mapping.unlower(obj[name], f"{context}.{name}")
                for name, mapping in self.fields.items()
                if name in obj
            }
        )


@dataclasses.dataclass
class DateTime:
    datetype: type

    def lower(self, obj, context):
        assert_isinstance(obj, self.datetype, context)
        return obj.isoformat()

    def unlower(self, obj, context):
        assert_isinstance(obj, str, context)
        return self.datetype.fromisoformat(obj)


@dataclasses.dataclass
class Enum:
    E: enum.Enum

    def lower(self, obj, context):
        assert_isinstance(obj, self.E, context)
        return obj.name

    def unlower(self, obj, context):
        assert_isinstance(obj, str, context)
        assert_in(obj, self.E.__members__, context)
        return getattr(self.E, obj)


@dataclasses.dataclass
class Signature:
    signature: typing.Any
    mappings: dict[str, Mapping]

    def lower(self, obj, context):
        assert_isinstance(obj, inspect.BoundArguments, context)
        return {
            name: self.mappings[name].lower(v, f"{context}.{name}")
            for name, v in obj.arguments.items()
        }

    def unlower(self, obj, context):
        assert_isinstance(obj, dict, context)
        return self.signature.bind(
            **{
                name: self.mappings[name].unlower(obj[name], f"{context}.{name}")
                for name in obj
            }
        )


@dataclasses.dataclass
class Reduce:
    T: type
    mapping: Mapping

    def lower(self, obj, context):
        f, args = obj.__reduce__()
        if f is not self.T:
            raise AGSError(f"reduction returned function {f}, expected {self.T}", context)
        if len(args) != 1:
            raise AGSError(f"reduction returned a tuple of length {len(args)}, expected 1", context)
        return self.mapping.lower(args[0], context)

    def unlower(self, obj, context):
        return self.T(self.mapping.unlower(obj, context))


mapping_with_date = functools.partial(mapping_for, context="", with_date=True)
mapping_without_date = functools.partial(mapping_for, context="", with_date=False)
