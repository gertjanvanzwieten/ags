from dataclasses import dataclass
from enum import Enum
from inspect import signature
import typing
from unittest import TestCase
from io import StringIO
from datetime import date, time, datetime
from doctest import DocFileSuite
import sys
import traceback

from ags import _mapping


def load_tests(loader, tests, ignore):
    if sys.version_info >= (3, 11):
        tests.addTests(DocFileSuite("README.md"))
    return tests


class Wrap:
    def __init__(self, obj):
        self._wrapped = obj

    def __hash__(self):
        return hash(self._wrapped)

    def __eq__(self, other):
        return isinstance(other, Wrap) and other._wrapped == self._wrapped

    def __str__(self):
        return f"<{self._wrapped!s}>"

    def __repr__(self):
        return f"<{self._wrapped!r}>"

    def unwrap(self):
        return self._wrapped


class WrapInject:
    def from_bool(obj: bool) -> Wrap:
        return Wrap(obj)

    def from_int(obj: int) -> Wrap:
        return Wrap(obj)

    def from_float(obj: float) -> Wrap:
        return Wrap(obj)

    def from_complex(obj: complex) -> Wrap:
        return Wrap(obj)

    def from_str(obj: str) -> Wrap:
        return Wrap(obj)

    def from_bytes(obj: bytes) -> Wrap:
        return Wrap(obj)

    def from_date(obj: date) -> Wrap:
        return Wrap(obj)

    def from_time(obj: time) -> Wrap:
        return Wrap(obj)

    def from_datetime(obj: datetime) -> Wrap:
        return Wrap(obj)

    def from_list(obj: list) -> Wrap:
        return Wrap(obj)

    def from_dict(obj: dict) -> Wrap:
        return Wrap(obj)

    def from_optional(obj: typing.Optional) -> Wrap:
        return Wrap(obj)

    def from_union(name: str, obj: typing.Any) -> Wrap:
        return Wrap((name, obj))


class WrapSurject:
    def to_bool(obj: Wrap) -> bool:
        return obj.unwrap()

    def to_int(obj: Wrap) -> int:
        return obj.unwrap()

    def to_float(obj: Wrap) -> float:
        return obj.unwrap()

    def to_complex(obj: Wrap) -> complex:
        return obj.unwrap()

    def to_str(obj: Wrap) -> str:
        return obj.unwrap()

    def to_bytes(obj: Wrap) -> bytes:
        return obj.unwrap()

    def to_date(obj: Wrap) -> date:
        return obj.unwrap()

    def to_time(obj: Wrap) -> time:
        return obj.unwrap()

    def to_datetime(obj: Wrap) -> datetime:
        return obj.unwrap()

    def to_list(obj: Wrap) -> list:
        return obj.unwrap()

    def to_dict(obj: Wrap) -> dict:
        return obj.unwrap()

    def to_optional(obj: Wrap) -> typing.Optional:
        return obj.unwrap()

    def to_union(obj: Wrap) -> tuple[str, typing.Any]:
        return obj.unwrap()


class Mapping(TestCase):
    def check(self, obj, T):
        m = _mapping.mapping_for(T)
        low = m.lower(obj, WrapInject)
        high = m.unlower(low, WrapSurject)
        self.assertEqual(high, obj)
        return low

    def test_primitive(self):
        for obj in "abc", 123, 1.5, True, False:
            T = type(obj)
            with self.subTest(T.__name__):
                self.assertEqual(self.check(obj, T), Wrap(obj))

    def test_literal(self):
        T = typing.Literal["abc", "xyz"]
        for obj in "abc", "xyz":
            self.assertEqual(self.check(obj, T), Wrap(obj))

    def test_complex(self):
        self.assertEqual(self.check(1 + 2j, complex), Wrap(1 + 2j))
        self.assertEqual(self.check(3 + 0j, complex), Wrap(3 + 0j))

    def test_bytes(self):
        self.check(b"abc", bytes)

    def test_list(self):
        for modern in False, True:
            with self.subTest(modern=modern):
                List = list if modern else typing.List
                self.assertEqual(
                    self.check([1, 2, 3], List[int]), Wrap([Wrap(1), Wrap(2), Wrap(3)])
                )

    def test_tuple(self):
        for modern in False, True:
            Tuple = tuple if modern else typing.Tuple
            with self.subTest("uniform", modern=modern):
                self.assertEqual(
                    self.check((1, 2, 3), Tuple[int, ...]),
                    Wrap([Wrap(1), Wrap(2), Wrap(3)]),
                )
            with self.subTest("pluriform", modern=modern):
                self.assertEqual(
                    self.check((123, "abc"), Tuple[int, str]),
                    Wrap([Wrap(123), Wrap("abc")]),
                )

    def test_dict(self):
        for modern in False, True:
            with self.subTest(modern=modern):
                Dict = dict if modern else typing.Dict
                self.assertEqual(
                    self.check({"a": 10, "b": 20}, Dict[str, int]),
                    Wrap({Wrap("a"): Wrap(10), Wrap("b"): Wrap(20)}),
                )

    def test_dataclass(self):
        @dataclass
        class A:
            i: int
            s: str

        self.assertEqual(
            self.check(A(123, "abc"), A),
            Wrap({Wrap("i"): Wrap(123), Wrap("s"): Wrap("abc")}),
        )

    def test_dataclass_defaults(self):
        @dataclass
        class A:
            i: int = 10
            s: str = 20

        with self.assertRaises(TypeError) as cm:
            _mapping.mapping_for(A)
        s = traceback.format_exception(cm.exception)
        self.assertEqual(
            s,
            [
                "TypeError: expects str, got int\n",
                "In: .s(default)\n",
            ]
            if sys.version_info >= (3, 11)
            else [
                "TypeError: expects str, got int\n",
            ],
        )

    def test_boundargs(self):
        def f(i: int, s: str):
            pass

        sig = signature(f)
        bound = sig.bind(123, "abc")
        self.assertEqual(
            self.check(bound, sig), Wrap({Wrap("i"): Wrap(123), Wrap("s"): Wrap("abc")})
        )

    def test_boundargs_defaults(self):
        def f(i: int = 10, s: str = 20):
            pass

        sig = signature(f)
        with self.assertRaises(TypeError) as cm:
            _mapping.mapping_for(sig)
        s = traceback.format_exception(cm.exception)
        self.assertEqual(
            s,
            [
                "TypeError: expects str, got int\n",
                "In: .s(default)\n",
            ]
            if sys.version_info >= (3, 11)
            else [
                "TypeError: expects str, got int\n",
            ],
        )

    def test_union(self):
        for modern in False, True:
            with self.subTest("optional", modern=modern):
                T = int | None if modern else typing.Optional[int]
                self.assertEqual(self.check(123, T), Wrap(Wrap(123)))
                self.assertEqual(self.check(None, T), Wrap(None))
            with self.subTest("union", modern=modern):
                T = int | str if modern else typing.Union[int, str]
                self.assertEqual(self.check(123, T), Wrap(("int", Wrap(123))))
                self.assertEqual(self.check("abc", T), Wrap(("str", Wrap("abc"))))
            with self.subTest("optional-union", modern=modern):
                T = (
                    int | str | None
                    if modern
                    else typing.Optional[typing.Union[int, str]]
                )
                self.assertEqual(
                    self.check(123, T),
                    Wrap(Wrap(("int", Wrap(123)))),
                )
                self.assertEqual(
                    self.check("abc", T),
                    Wrap(Wrap(("str", Wrap("abc")))),
                )
                self.assertEqual(self.check(None, T), Wrap(None))

    def test_enum(self):
        class E(Enum):
            a = 1
            b = 2

        self.assertEqual(self.check(E.a, E), Wrap("a"))
        self.assertEqual(self.check(E.b, E), Wrap("b"))

    def test_reduce(self):
        if sys.version_info < (3, 11):
            self.skipTest("reduce is supported as of Python 3.11")

        for modern in False, True:
            with self.subTest(modern=modern):
                List = list if modern else typing.List
                Tuple = tuple if modern else typing.Tuple
                Type = type if modern else typing.Type

                class A:
                    def __init__(self, x: List[int]):
                        self.x = x

                    def __reduce__(
                        self,
                    ) -> Tuple[Type[typing.Self], Tuple[List[int]]]:
                        return A, (self.x,)

                    def __eq__(self, other):
                        return isinstance(other, A) and other.x == self.x

                a = A([2, 3, 4])
                self.assertEqual(self.check(a, A), Wrap([Wrap(2), Wrap(3), Wrap(4)]))

    def test_ags_reduce(self):
        class A:
            def __init__(self, x: int):
                self.x = x

            def __into_ags__(self) -> int:
                return self.x

            @classmethod
            def __from_ags__(cls, obj: int):
                return cls(obj)

            def __eq__(self, other):
                return isinstance(other, A) and other.x == self.x

        a = A(5)
        self.assertEqual(self.check(a, A), Wrap(5))

    def test_exception(self):
        T = dict[str, list[int]]
        m = _mapping.mapping_for(T)
        with self.assertRaises(TypeError) as cm:
            m.unlower(
                Wrap(
                    {
                        Wrap("a"): Wrap([Wrap(10), Wrap(20)]),
                        Wrap("b"): Wrap([Wrap(30), Wrap("40"), Wrap(50)]),
                    }
                ),
                WrapSurject,
            )
        s = traceback.format_exception(cm.exception)
        self.assertEqual(
            s,
            [
                "TypeError: expects int, got str\n",
                "In: [b][1]\n",
            ]
            if sys.version_info >= (3, 11)
            else [
                "TypeError: expects int, got str\n",
            ],
        )


class Demo:
    @dataclass
    class A:
        x: int
        y: float

    @dataclass
    class B:
        @dataclass
        class Sub:
            b: bytes
            greek: typing.Optional[str]

        abc: typing.Literal["a", "b", "c"]
        sub: Sub

    @dataclass
    class Left:
        b: bool

    @dataclass
    class Right:
        when: datetime

    def func(a: A, b: typing.List[B], direction: typing.Union[Left, Right]):
        pass


class Backend:
    def check_bool(self, obj):
        low = self.mod._inject.from_bool(obj)
        high = self.mod._surject.to_bool(low)
        self.assertEqual(high, obj)
        return low

    def check_int(self, obj):
        low = self.mod._inject.from_int(obj)
        high = self.mod._surject.to_int(low)
        self.assertEqual(high, obj)
        return low

    def check_float(self, obj):
        low = self.mod._inject.from_float(obj)
        high = self.mod._surject.to_float(low)
        self.assertEqual(high, obj)
        return low

    def check_complex(self, obj):
        low = self.mod._inject.from_complex(obj)
        high = self.mod._surject.to_complex(low)
        self.assertEqual(high, obj)
        return low

    def check_str(self, obj):
        low = self.mod._inject.from_str(obj)
        high = self.mod._surject.to_str(low)
        self.assertEqual(high, obj)
        return low

    def check_bytes(self, obj):
        low = self.mod._inject.from_bytes(obj)
        high = self.mod._surject.to_bytes(low)
        self.assertEqual(high, obj)
        return low

    def check_date(self, obj):
        low = self.mod._inject.from_date(obj)
        high = self.mod._surject.to_date(low)
        self.assertEqual(high, obj)
        return low

    def check_time(self, obj):
        low = self.mod._inject.from_time(obj)
        high = self.mod._surject.to_time(low)
        self.assertEqual(high, obj)
        return low

    def check_datetime(self, obj):
        low = self.mod._inject.from_datetime(obj)
        high = self.mod._surject.to_datetime(low)
        self.assertEqual(high, obj)
        return low

    def check_list(self, obj):
        low = self.mod._inject.from_list(obj)
        high = self.mod._surject.to_list(low)
        self.assertEqual(high, obj)
        return low

    def check_dict(self, obj):
        low = self.mod._inject.from_dict(obj)
        high = self.mod._surject.to_dict(low)
        self.assertEqual(high, obj)
        return low

    def check_optional(self, obj):
        low = self.mod._inject.from_optional(obj)
        high = self.mod._surject.to_optional(low)
        self.assertEqual(high, obj)
        return low

    def check_union(self, name, obj):
        low = self.mod._inject.from_union(name, obj)
        name_, high = self.mod._surject.to_union(low)
        self.assertEqual(name, name_)
        self.assertEqual(high, obj)
        return low

    def check_load_dump(self, expect):
        sig = signature(Demo.func)
        bound = sig.bind(
            a=Demo.A(1, 2.5),
            b=[
                Demo.B("a", Demo.B.Sub(b"foo", "αβγ")),
                Demo.B("b", Demo.B.Sub(b"bar", None)),
            ],
            direction=Demo.Right(datetime.fromisoformat("2025-07-27T09:06:40")),
        )
        with self.subTest("load"):
            obj = self.mod.load(StringIO(expect), sig)
            self.assertEqual(obj, bound)
        with self.subTest("loads"):
            obj = self.mod.loads(expect, sig)
            self.assertEqual(obj, bound)
        with self.subTest("dump"):
            f = StringIO()
            self.mod.dump(f, bound, sig)
            self.assertEqual(f.getvalue(), expect)
        with self.subTest("dumps"):
            s = self.mod.dumps(bound, sig)
            self.assertEqual(s, expect)


class JSON(Backend, TestCase):
    from ags import json as mod

    def test_bool(self):
        for obj in True, False:
            self.assertEqual(self.check_bool(obj), obj)

    def test_int(self):
        for obj in 0, 1, 2, 10, -5:
            self.assertEqual(self.check_int(obj), obj)

    def test_float(self):
        for obj in 0.0, 1.0, 2.0, -2.5:
            self.assertEqual(self.check_float(obj), obj)

    def test_complex(self):
        for obj in 0 + 0j, 1 + 0j:
            self.assertEqual(self.check_complex(obj), obj.real)
        self.assertEqual(self.check_complex(1j), "1j")
        self.assertEqual(self.check_complex(-2.5 + 3.5j), "-2.5+3.5j")

    def test_str(self):
        for obj in "foo", "bar":
            self.assertEqual(self.check_str(obj), obj)

    def test_bytes(self):
        for obj in b"foo", b"bar", "αβγ".encode():
            self.assertEqual(self.check_bytes(obj), "utf8:" + obj.decode("utf8"))
        self.assertEqual(self.check_bytes(bytes([0xC0, 0xC1, 0xF5])), "z`^w")

    def test_date(self):
        for obj in (
            date.fromisoformat("2000-10-15"),
            date.fromisoformat("2025-12-31"),
        ):
            self.assertEqual(self.check_date(obj), obj.isoformat())

    def test_time(self):
        for obj in (
            time.fromisoformat("10:32"),
            time.fromisoformat("22:33"),
        ):
            self.assertEqual(self.check_time(obj), obj.isoformat())

    def test_datetime(self):
        for obj in (
            datetime.fromisoformat("2000-10-15 10:32"),
            datetime.fromisoformat("2025-12-31 22:33"),
        ):
            self.assertEqual(self.check_datetime(obj), obj.isoformat())

    def test_list(self):
        obj = [123, "abc", ["x", "y", "z"]]
        self.assertEqual(self.check_list(obj), obj)

    def test_dict(self):
        obj = {"a": 123, 10: "abc", True: ["x", "y", "z"]}
        self.assertEqual(self.check_dict(obj), obj)

    def test_union(self):
        self.assertEqual(self.check_union("abc", 123), {"abc": 123})

    def test_optional(self):
        self.assertEqual(self.check_optional("abc"), "abc")
        self.assertEqual(self.check_optional(None), None)

    def test_load_dump(self):
        self.check_load_dump("""\
{
  "a": {
    "x": 1,
    "y": 2.5
  },
  "b": [
    {
      "abc": "a",
      "sub": {
        "b": "utf8:foo",
        "greek": "αβγ"
      }
    },
    {
      "abc": "b",
      "sub": {
        "b": "utf8:bar",
        "greek": null
      }
    }
  ],
  "direction": {
    "Right": {
      "when": "2025-07-27T09:06:40"
    }
  }
}
""")


class YAML(JSON):
    from ags import yaml as mod

    def test_load_dump(self):
        self.check_load_dump("""\
a:
  x: 1
  y: 2.5
b:
  - abc: a
    sub:
      b: "utf8:foo"
      greek: αβγ
  - abc: b
    sub:
      b: "utf8:bar"
      greek: ~
direction:
  Right:
    when: "2025-07-27T09:06:40"
""")


class UCSL(Backend, TestCase):
    from ags import ucsl as mod

    def test_bool(self):
        self.assertEqual(self.check_bool(True), "true")
        self.assertEqual(self.check_bool(False), "false")

    def test_int(self):
        for obj in 0, 1, 2, 10, -5:
            self.assertEqual(self.check_int(obj), str(obj))

    def test_float(self):
        for obj in 0.0, 1.0, 2.0, -2.5:
            self.assertEqual(self.check_float(obj), str(obj))

    def test_complex(self):
        for obj in 0 + 0j, 1 + 0j, 0 + 1j, -2.5 + 3.5j:
            self.assertEqual(self.check_complex(obj), str(obj).lstrip("(").rstrip(")"))

    def test_str(self):
        for obj in "foo", "bar":
            self.assertEqual(self.check_str(obj), obj)

    def test_bytes(self):
        for obj in b"foo", b"bar", "αβγ".encode():
            self.assertEqual(self.check_bytes(obj), "utf8:" + obj.decode("utf8"))
        self.assertEqual(self.check_bytes(bytes([0xC0, 0xC1, 0xF5])), "z`^w")

    def test_date(self):
        for obj in (
            date.fromisoformat("2000-10-15"),
            date.fromisoformat("2025-12-31"),
        ):
            self.assertEqual(self.check_date(obj), obj.isoformat())

    def test_time(self):
        for obj in (
            time.fromisoformat("10:32"),
            time.fromisoformat("22:33"),
        ):
            self.assertEqual(self.check_time(obj), obj.isoformat())

    def test_datetime(self):
        for obj in (
            datetime.fromisoformat("2000-10-15 10:32"),
            datetime.fromisoformat("2025-12-31 22:33"),
        ):
            self.assertEqual(self.check_datetime(obj), obj.isoformat())

    def test_list(self):
        self.assertEqual(self.check_list(["123", "abc", "xyz"]), "123,abc,xyz")
        self.assertEqual(self.check_list([]), "")
        self.assertEqual(self.check_list(["", ""]), ",")
        self.assertEqual(self.check_list([""]), "[]")

    def test_dict(self):
        self.assertEqual(
            self.check_dict({"a": "123", "b": "abc", "c": "xyz"}), "a=123,b=abc,c=xyz"
        )
        self.assertEqual(self.check_dict({}), "")

    def test_union(self):
        self.assertEqual(self.check_union("abc", "123"), "abc[123]")
        self.assertEqual(self.check_union("abc", ""), "abc")

    def test_optional(self):
        self.assertEqual(self.check_optional("abc"), "abc")
        self.assertEqual(self.check_optional("-"), "~-")
        self.assertEqual(self.check_optional("~-"), "~~-")
        self.assertEqual(self.check_optional("a-z"), "a-z")
        self.assertEqual(self.check_optional(None), "-")

    def test_load_dump(self):
        self.check_load_dump(
            "a=[x=1,y=2.5],b=[[abc=a,sub=[b=utf8:foo,greek=αβγ]],[abc=b,sub=[b=utf8:bar,greek=-]]],direction=Right[when=2025-07-27T09:06:40]"
        )

    ## internals

    def test_balance(self):
        self.assertEqual(self.mod._balance("foo", "x"), (0, 0))
        self.assertEqual(self.mod._balance("foo[bar", "o"), (1, 2))
        self.assertEqual(self.mod._balance("foo[bar", "a"), (0, 1))
        self.assertEqual(self.mod._balance("foo]bar", "x"), (1, 0))
        self.assertEqual(self.mod._balance("[foobar]", "x"), (0, 0))
        self.assertEqual(self.mod._balance("[foobar]", "a"), (0, 0))
        self.assertEqual(self.mod._balance("[foo][bar]", "x"), (0, 0))
        self.assertEqual(self.mod._balance("foo]bar]baz", "x"), (2, 0))
        self.assertEqual(self.mod._balance("foo]bar]baz", "r"), (2, 0))
        self.assertEqual(self.mod._balance("foo]bar]baz", "z"), (3, 1))
        self.assertEqual(self.mod._balance("foo][bar", "x"), (1, 1))

    def check_cover(self, s, chars):
        hidden = self.mod._cover(s, chars)
        self.assertEqual(self.mod._expose(hidden), s)
        return hidden

    def test_cover(self):
        self.assertEqual(self.check_cover("foo", "o"), "[foo]")
        self.assertEqual(self.check_cover("foo", "a"), "foo")
        self.assertEqual(self.check_cover("[foo]", "o"), "~[foo]~")
        self.assertEqual(self.check_cover("[foo", "o"), "~[foo~]")
        self.assertEqual(self.check_cover("foo][bar", "o"), "[foo][bar]")
        self.assertEqual(self.check_cover("foo]bar]baz", "o"), "[[~foo]bar]baz~")
