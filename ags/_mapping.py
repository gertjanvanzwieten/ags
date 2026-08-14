import dataclasses
import datetime
import enum
import inspect
import typing
import types
import sys


class context:
    def __init__(self, context):
        self.context = context

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        if not exc_value:
            return
        if not hasattr(exc_value, "__notes__"):
            notes = []
            exc_value.__notes__ = notes
        else:
            notes = exc_value.__notes__
        note = "In: " + self.context
        if notes and notes[-1].startswith("In: "):
            note += notes.pop()[4:]
        notes.append(note)


def assert_isinstance(obj, T):
    if type(obj) is not T:
        raise TypeError(f"expects {T.__name__}, got {type(obj).__name__}")
    return obj


def assert_in(obj, options):
    if obj not in options:
        raise ValueError(f"expects one of {', '.join(map(repr, options))}, got {obj!r}")


class Inject(typing.Protocol):
    def from_bool(obj: bool) -> typing.Any: ...
    def from_int(obj: int) -> typing.Any: ...
    def from_float(obj: float) -> typing.Any: ...
    def from_complex(obj: complex) -> typing.Any: ...
    def from_str(obj: str) -> typing.Any: ...
    def from_bytes(obj: bytes) -> typing.Any: ...
    def from_date(obj: datetime.date) -> typing.Any: ...
    def from_time(obj: datetime.time) -> typing.Any: ...
    def from_datetime(obj: datetime.datetime) -> typing.Any: ...
    def from_list(obj: list) -> typing.Any: ...
    def from_dict(obj: dict) -> typing.Any: ...
    def from_optional(obj: typing.Optional) -> typing.Any: ...
    def from_union(name: str, obj: typing.Any) -> typing.Any: ...


class Surject(typing.Protocol):
    def to_bool(obj: typing.Any) -> bool: ...
    def to_int(obj: typing.Any) -> int: ...
    def to_float(obj: typing.Any) -> float: ...
    def to_complex(obj: typing.Any) -> complex: ...
    def to_str(obj: typing.Any) -> str: ...
    def to_bytes(obj: typing.Any) -> bytes: ...
    def to_date(obj: typing.Any) -> datetime.date: ...
    def to_time(obj: typing.Any) -> datetime.time: ...
    def to_datetime(obj: typing.Any) -> datetime.datetime: ...
    def to_list(obj: typing.Any) -> list: ...
    def to_dict(obj: typing.Any) -> dict: ...
    def to_optional(obj: typing.Any) -> typing.Optional: ...
    def to_union(obj: typing.Any) -> typing.Tuple[str, typing.Any]: ...


class Mapping(typing.Protocol):
    def lower(self, obj: typing.Any, inject: Inject) -> typing.Any: ...
    def unlower(self, obj: typing.Any, surject: Surject) -> typing.Any: ...


def mapping_for(T) -> Mapping:
    if T is bool:
        return Bool()

    if T is int:
        return Int()

    if T is float:
        return Float()

    if T is complex:
        return Complex()

    if T is str:
        return Str()

    if T is bytes:
        return Bytes()

    if T is datetime.date:
        return Date()

    if T is datetime.time:
        return Time()

    if T is datetime.datetime:
        return DateTime()

    if typing.get_origin(T) == typing.Literal:
        options = typing.get_args(T)
        T = type(options[0])
        if all(type(option) is T for option in options[1:]):
            return Literal(mapping_for(T), options)

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
                mapping = mapping_for(field.type)
                fields[field.name] = mapping
                if field.default is not dataclasses.MISSING:
                    with context("(default)"):
                        mapping.lower(field.default, Inject)
        return DataClass(T, Str(), fields)

    if type(T) is type(enum.Enum):
        return Enum(T)

    if isinstance(T, inspect.Signature):
        mappings = {}
        for param in T.parameters.values():
            with context(f".{param.name}"):
                if param.kind not in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY):
                    raise TypeError("positional-only arguments are not supported")
                if param.annotation is not param.empty:
                    mapping = mapping_for(param.annotation)
                    if param.default is not param.empty:
                        with context("(default)"):
                            mapping.lower(param.default, Inject)
                elif param.default is not param.empty:
                    mapping = mapping_for(type(param.default))
                else:
                    raise TypeError(f"cannot establish type for parameter {param.name}")
                mappings[param.name] = mapping
        return Signature(T, Str(), mappings)

    if sys.version_info >= (3, 11) and hasattr(T, "__reduce__"):
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

    if hasattr(T, "__into_ags__") and hasattr(T, "__from_ags__"):
        annotation = inspect.signature(T.__into_ags__).return_annotation
        return AGSReduce(T, mapping_for(annotation))

    raise ValueError(f"cannot find a mapping for type {T!r}")


class Bool:
    def lower(self, obj, inject):
        return inject.from_bool(assert_isinstance(obj, bool))

    def unlower(self, obj, surject):
        return assert_isinstance(surject.to_bool(obj), bool)


class Int:
    def lower(self, obj, inject):
        return inject.from_int(assert_isinstance(obj, int))

    def unlower(self, obj, surject):
        return assert_isinstance(surject.to_int(obj), int)


class Float:
    def lower(self, obj, inject):
        return inject.from_float(assert_isinstance(obj, float))

    def unlower(self, obj, surject):
        return assert_isinstance(surject.to_float(obj), float)


class Complex:
    def lower(self, obj, inject):
        return inject.from_complex(assert_isinstance(obj, complex))

    def unlower(self, obj, surject):
        return assert_isinstance(surject.to_complex(obj), complex)


class Str:
    def lower(self, obj, inject):
        return inject.from_str(assert_isinstance(obj, str))

    def unlower(self, obj, surject):
        return assert_isinstance(surject.to_str(obj), str)


class Bytes:
    def lower(self, obj, inject):
        return inject.from_bytes(assert_isinstance(obj, bytes))

    def unlower(self, obj, surject):
        return assert_isinstance(surject.to_bytes(obj), bytes)


class Date:
    def lower(self, obj, inject):
        return inject.from_date(assert_isinstance(obj, datetime.date))

    def unlower(self, obj, surject):
        return assert_isinstance(surject.to_date(obj), datetime.date)


class Time:
    def lower(self, obj, inject):
        return inject.from_time(assert_isinstance(obj, datetime.time))

    def unlower(self, obj, surject):
        return assert_isinstance(surject.to_time(obj), datetime.time)


class DateTime:
    def lower(self, obj, inject):
        return inject.from_datetime(assert_isinstance(obj, datetime.datetime))

    def unlower(self, obj, surject):
        return assert_isinstance(surject.to_datetime(obj), datetime.datetime)


@dataclasses.dataclass
class Literal:
    mapping: Mapping
    options: tuple[typing.Any, ...]

    def lower(self, obj, inject):
        assert_in(obj, self.options)
        return self.mapping.lower(obj, inject)

    def unlower(self, obj, surject):
        v = self.mapping.unlower(obj, surject)
        assert_in(v, self.options)
        return v


@dataclasses.dataclass
class Optional:
    mapping: Mapping

    def lower(self, obj, inject):
        return inject.from_optional(
            None if obj is None else self.mapping.lower(obj, inject)
        )

    def unlower(self, obj, surject):
        value = surject.to_optional(obj)
        if value is None:
            return None
        return self.mapping.unlower(value, surject)


@dataclasses.dataclass
class Union:
    options: dict[str, tuple[typing.Any, Mapping]]

    def lower(self, obj, inject):
        for name, (T, mapping) in self.options.items():
            if type(obj) is T:
                with context(f"({name})"):
                    return inject.from_union(name, mapping.lower(obj, inject))
        raise ValueError(
            f"expects one of {', '.join(self.options)}, got {type(obj).__name__}"
        )

    def unlower(self, obj, surject):
        name, value = surject.to_union(obj)
        assert_in(name, self.options)
        T, mapping = self.options[name]
        with context(f"({name})"):
            return mapping.unlower(value, surject)


@dataclasses.dataclass
class List:
    mapping: Mapping

    def lower(self, obj, inject):
        assert_isinstance(obj, list)
        items = []
        for i, item in enumerate(obj):
            with context(f"[{i}]"):
                items.append(self.mapping.lower(item, inject))
        return inject.from_list(items)

    def unlower(self, obj, surject):
        lobj = surject.to_list(obj)
        assert_isinstance(lobj, list)
        items = []
        for i, item in enumerate(lobj):
            with context(f"[{i}]"):
                items.append(self.mapping.unlower(item, surject))
        return items


@dataclasses.dataclass
class Tuple:
    mappings: tuple[Mapping, ...]

    def lower(self, obj, inject):
        assert_isinstance(obj, tuple)
        if len(obj) != len(self.mappings):
            raise ValueError(f"expects {len(self.mappings)} items, got {len(obj)}")
        items = []
        for i, (item, mapping) in enumerate(zip(obj, self.mappings)):
            with context(f"[{i}]"):
                items.append(mapping.lower(item, inject))
        return inject.from_list(items)

    def unlower(self, obj, surject):
        lobj = surject.to_list(obj)
        assert_isinstance(lobj, list)
        if len(lobj) != len(self.mappings):
            raise ValueError(f"expects {len(self.mappings)} items, got {len(lobj)}")
        items = []
        for i, (item, mapping) in enumerate(zip(lobj, self.mappings)):
            with context(f"[{i}]"):
                items.append(mapping.unlower(item, surject))
        return tuple(items)


@dataclasses.dataclass
class UniformTuple:
    mapping: Mapping

    def lower(self, obj, inject):
        assert_isinstance(obj, tuple)
        items = []
        for i, item in enumerate(obj):
            with context(f"[{i}]"):
                items.append(self.mapping.lower(item, inject))
        return inject.from_list(items)

    def unlower(self, obj, surject):
        lobj = surject.to_list(obj)
        assert_isinstance(lobj, list)
        items = []
        for i, item in enumerate(lobj):
            with context(f"[{i}]"):
                items.append(self.mapping.unlower(item, surject))
        return tuple(items)


@dataclasses.dataclass
class Dict:
    key_mapping: Mapping
    val_mapping: Mapping

    def lower(self, obj, inject):
        assert_isinstance(obj, dict)
        d = {}
        for k, v in obj.items():
            with context(f"[{k}]"):
                d[self.key_mapping.lower(k, inject)] = self.val_mapping.lower(v, inject)
        return inject.from_dict(d)

    def unlower(self, obj, surject):
        dobj = surject.to_dict(obj)
        assert_isinstance(dobj, dict)
        d = {}
        for k, v in dobj.items():
            name = self.key_mapping.unlower(k, surject)
            with context(f"[{name}]"):
                d[name] = self.val_mapping.unlower(v, surject)
        return d


@dataclasses.dataclass
class DataClass:
    cls: type
    key_mapping: Mapping
    fields: dict[str, Mapping]

    def lower(self, obj, inject):
        if not dataclasses.is_dataclass(obj) or isinstance(obj, type):
            raise TypeError(f"expects a dataclass object, got {type(obj).__name__}")
        d = {}
        for name, mapping in self.fields.items():
            with context(f".{name}"):
                d[self.key_mapping.lower(name, inject)] = mapping.lower(
                    getattr(obj, name), inject
                )
        return inject.from_dict(d)

    def unlower(self, obj, surject):
        dobj = surject.to_dict(obj)
        d = {}
        for k, value in dobj.items():
            name = self.key_mapping.unlower(k, surject)
            mapping = self.fields.get(name)
            if mapping is None:
                raise ValueError(f"invalid field: {name!r}")
            with context(f".{name}"):
                d[name] = mapping.unlower(value, surject)
        return self.cls(**d)


@dataclasses.dataclass
class Enum:
    E: enum.Enum

    def lower(self, obj, inject):
        assert_isinstance(obj, self.E)
        return inject.from_str(obj.name)

    def unlower(self, obj, surject):
        name = surject.to_str(obj)
        assert_isinstance(name, str)
        assert_in(name, self.E.__members__)
        return getattr(self.E, name)


@dataclasses.dataclass
class Signature:
    signature: typing.Any
    key_mapping: Mapping
    val_mappings: dict[str, Mapping]

    def lower(self, obj, inject):
        assert_isinstance(obj, inspect.BoundArguments)
        if obj.signature != self.signature:
            raise ValueError("arguments are bound to the wrong signature")
        obj = self.signature.bind(*obj.args, **obj.kwargs)  # copy obj
        obj.apply_defaults()  # modify in place
        d = {}
        for name, v in obj.arguments.items():
            with context(f".{name}"):
                d[self.key_mapping.lower(name, inject)] = self.val_mappings[name].lower(
                    v, inject
                )
        return inject.from_dict(d)

    def unlower(self, obj, surject):
        dobj = surject.to_dict(obj)
        assert_isinstance(dobj, dict)
        d = {}
        for k, v in dobj.items():
            name = self.key_mapping.unlower(k, surject)
            with context(f".{name}"):
                d[name] = self.val_mappings[name].unlower(v, surject)
        return self.signature.bind(**d)


@dataclasses.dataclass
class Reduce:
    T: type
    mapping: Mapping

    def lower(self, obj, inject):
        assert_isinstance(obj, self.T)
        f, args = obj.__reduce__()
        if f is not self.T:
            raise ValueError(f"reduction returned function {f}, expected {self.T}")
        if len(args) != 1:
            raise ValueError(
                f"reduction returned a tuple of length {len(args)}, expected 1"
            )
        return self.mapping.lower(args[0], inject)

    def unlower(self, obj, surject):
        return self.T(self.mapping.unlower(obj, surject))


@dataclasses.dataclass
class AGSReduce:
    T: type
    mapping: Mapping

    def lower(self, obj, inject):
        assert_isinstance(obj, self.T)
        return self.mapping.lower(obj.__into_ags__(), inject)

    def unlower(self, obj, surject):
        return self.T.__from_ags__(self.mapping.unlower(obj, surject))
