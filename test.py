from dataclasses import dataclass
from enum import Enum
from inspect import signature
from typing import Union, Literal, Tuple, List, Dict, Optional, Self, Type
from unittest import TestCase
from io import StringIO
from datetime import date, time, datetime
from doctest import DocFileSuite

from ags import _mapping


def load_tests(loader, tests, ignore):
    tests.addTests(DocFileSuite("README.md"))
    return tests


class Mapping(TestCase):
    class IdentityBackend:
        def lower(obj):
            return obj

        def unlower(obj, T):
            if type(obj) is not T:
                raise ValueError(f"expects {T.__name__}, got {type(obj).__name__}")
            return obj

    def check(self, obj, T):
        m = _mapping.mapping_for(T)
        low = m.lower(obj, self.IdentityBackend)
        high = m.unlower(low, self.IdentityBackend)
        self.assertEqual(high, obj)
        return low

    def test_primitive(self):
        for obj in "abc", 123, 1.5, True, False:
            T = type(obj)
            with self.subTest(T.__name__):
                self.assertEqual(self.check(obj, T), obj)

    def test_literal(self):
        T = Literal["abc", 123]
        for obj in "abc", 123:
            self.assertEqual(self.check(obj, T), obj)

    def test_complex(self):
        self.assertEqual(self.check(1 + 2j, complex), 1 + 2j)
        self.assertEqual(self.check(3 + 0j, complex), 3 + 0j)

    def test_bytes(self):
        self.check(b"abc", bytes)

    def test_list(self):
        self.assertEqual(self.check([1, 2, 3], List[int]), [1, 2, 3])

    def test_tuple(self):
        with self.subTest("uniform"):
            self.assertEqual(self.check((1, 2, 3), Tuple[int, ...]), [1, 2, 3])
        with self.subTest("pluriform"):
            self.assertEqual(self.check((123, "abc"), Tuple[int, str]), [123, "abc"])

    def test_dict(self):
        self.assertEqual(
            self.check({"a": 10, "b": 20}, Dict[str, int]), {"a": 10, "b": 20}
        )

    def test_dataclass(self):
        @dataclass
        class A:
            i: int
            s: str

        self.assertEqual(self.check(A(123, "abc"), A), {"i": 123, "s": "abc"})

    def test_boundargs(self):
        def f(i: int, s: str):
            pass

        sig = signature(f)
        bound = sig.bind(123, "abc")
        self.assertEqual(self.check(bound, sig), {"i": 123, "s": "abc"})

    def test_union(self):
        for modern in False, True:
            with self.subTest("optional", modern=modern):
                T = int | None if modern else Optional[int]
                self.assertEqual(self.check(123, T), _mapping.OptionalValue(123))
                self.assertEqual(self.check(None, T), _mapping.OptionalValue(None))
            with self.subTest("union", modern=modern):
                T = int | str if modern else Union[int, str]
                self.assertEqual(self.check(123, T), _mapping.UnionValue("int", 123))
                self.assertEqual(
                    self.check("abc", T), _mapping.UnionValue("str", "abc")
                )
            with self.subTest("optional-union", modern=modern):
                T = int | str | None if modern else Optional[Union[int, str]]
                self.assertEqual(
                    self.check(123, T),
                    _mapping.OptionalValue(_mapping.UnionValue("int", 123)),
                )
                self.assertEqual(
                    self.check("abc", T),
                    _mapping.OptionalValue(_mapping.UnionValue("str", "abc")),
                )
                self.assertEqual(self.check(None, T), _mapping.OptionalValue(None))

    def test_enum(self):
        class E(Enum):
            a = 1
            b = 2

        self.assertEqual(self.check(E.a, E), "a")
        self.assertEqual(self.check(E.b, E), "b")

    def test_reduce(self):
        class A:
            def __init__(self, x: List[int]):
                self.x = x

            def __reduce__(self) -> Tuple[Type[Self], Tuple[List[int]]]:
                return A, (self.x,)

            def __eq__(self, other):
                return isinstance(other, A) and other.x == self.x

        a = A([2, 3, 4])
        self.assertEqual(self.check(a, A), [2, 3, 4])

    def test_exception(self):
        T = dict[str, list[int]]
        m = _mapping.mapping_for(T)
        with self.assertRaisesRegex(ValueError, "in \[b\]\[1\]: expects int, got str"):
            m.unlower({"a": [10, 20], "b": [30, "40", 50]}, self.IdentityBackend)


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
            greek: Optional[str]

        abc: Literal["a", "b", "c"]
        sub: Sub

    @dataclass
    class Left:
        b: bool

    @dataclass
    class Right:
        when: datetime

    def func(a: A, b: List[B], direction: Union[Left, Right]):
        pass


class Backend:
    def check_lower(self, obj, expect):
        low = self.mod._Backend.lower(obj)
        self.assertEqual(low, expect)
        high = self.mod._Backend.unlower(low, type(obj))
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
            direction=Demo.Right(datetime.fromtimestamp(1753600000)),
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
            self.check_lower(obj, expect=obj)

    def test_int(self):
        for obj in 0, 1, 2, 10, -5:
            self.check_lower(obj, expect=obj)

    def test_float(self):
        for obj in 0.0, 1.0, 2.0, -2.5:
            self.check_lower(obj, expect=obj)

    def test_complex(self):
        for obj in 0 + 0j, 1 + 0j:
            self.check_lower(obj, expect=obj.real)
        self.check_lower(1j, expect="1j")
        self.check_lower(-2.5 + 3.5j, "-2.5+3.5j")

    def test_str(self):
        for obj in "foo", "bar":
            self.check_lower(obj, expect=obj)

    def test_bytes(self):
        for obj in b"foo", b"bar", "αβγ".encode():
            self.check_lower(obj, expect="utf8:" + obj.decode("utf8"))
        self.check_lower(bytes([0xC0, 0xC1, 0xF5]), expect="z`^w")

    def test_date(self):
        for obj in (
            date.fromisoformat("2000-10-15"),
            date.fromisoformat("2025-12-31"),
        ):
            self.check_lower(obj, expect=obj.isoformat())

    def test_time(self):
        for obj in (
            time.fromisoformat("10:32"),
            time.fromisoformat("22:33"),
        ):
            self.check_lower(obj, expect=obj.isoformat())

    def test_datetime(self):
        for obj in (
            datetime.fromisoformat("2000-10-15 10:32"),
            datetime.fromisoformat("2025-12-31 22:33"),
        ):
            self.check_lower(obj, expect=obj.isoformat())

    def test_list(self):
        obj = [123, "abc", ["x", "y", "z"]]
        self.check_lower(obj, expect=obj)

    def test_dict(self):
        obj = {"a": 123, 10: "abc", True: ["x", "y", "z"]}
        self.check_lower(obj, expect=obj)

    def test_union(self):
        self.check_lower(_mapping.UnionValue("abc", 123), expect={"abc": 123})

    def test_optional(self):
        self.check_lower(_mapping.OptionalValue("abc"), expect="abc")
        self.check_lower(_mapping.OptionalValue(None), expect=None)

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


class YAML(Backend, TestCase):
    from ags import yaml as mod

    def test_bool(self):
        for obj in True, False:
            self.check_lower(obj, expect=obj)

    def test_int(self):
        for obj in 0, 1, 2, 10, -5:
            self.check_lower(obj, expect=obj)

    def test_float(self):
        for obj in 0.0, 1.0, 2.0, -2.5:
            self.check_lower(obj, expect=obj)

    def test_complex(self):
        for obj in 0 + 0j, 1 + 0j:
            self.check_lower(obj, expect=obj.real)
        self.check_lower(1j, expect="1j")
        self.check_lower(-2.5 + 3.5j, "-2.5+3.5j")

    def test_str(self):
        for obj in "foo", "bar":
            self.check_lower(obj, expect=obj)

    def test_bytes(self):
        for obj in b"foo", b"bar", "αβγ".encode():
            self.check_lower(obj, expect=obj)

    def test_date(self):
        for obj in (
            date.fromisoformat("2000-10-15"),
            date.fromisoformat("2025-12-31"),
        ):
            self.check_lower(obj, expect=obj)

    def test_time(self):
        for obj in (
            time.fromisoformat("10:32"),
            time.fromisoformat("22:33"),
        ):
            self.check_lower(obj, expect=obj)

    def test_datetime(self):
        for obj in (
            datetime.fromisoformat("2000-10-15 10:32"),
            datetime.fromisoformat("2025-12-31 22:33"),
        ):
            self.check_lower(obj, expect=obj)

    def test_list(self):
        obj = [123, "abc", ["x", "y", "z"]]
        self.check_lower(obj, expect=obj)

    def test_dict(self):
        obj = {"a": 123, 10: "abc", True: ["x", "y", "z"]}
        self.check_lower(obj, expect=obj)

    def test_union(self):
        self.check_lower(_mapping.UnionValue("abc", 123), expect={"abc": 123})

    def test_optional(self):
        self.check_lower(_mapping.OptionalValue("abc"), expect="abc")
        self.check_lower(_mapping.OptionalValue(None), expect=None)

    def test_load_dump(self):
        self.check_load_dump("""\
a:
  x: 1
  y: 2.5
b:
- abc: a
  sub:
    b: !!binary |
      Zm9v
    greek: αβγ
- abc: b
  sub:
    b: !!binary |
      YmFy
    greek: null
direction:
  Right:
    when: 2025-07-27 09:06:40
""")
