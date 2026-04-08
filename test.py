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


class Mapping(TestCase):
    def myinject(self, obj):
        return obj

    def mysurject(self, obj, T):
        self.assertIs(type(obj), T)
        return obj

    def check(self, obj, T):
        m = _mapping.mapping_for(T)
        low = m.lower(obj, self.myinject)
        high = m.unlower(low, self.mysurject)
        self.assertEqual(high, obj)
        return low

    def test_primitive(self):
        for obj in "abc", 123, 1.5, True, False:
            T = type(obj)
            with self.subTest(T.__name__):
                self.assertEqual(self.check(obj, T), obj)

    def test_literal(self):
        T = typing.Literal["abc", 123]
        for obj in "abc", 123:
            self.assertEqual(self.check(obj, T), obj)

    def test_complex(self):
        self.assertEqual(self.check(1 + 2j, complex), 1 + 2j)
        self.assertEqual(self.check(3 + 0j, complex), 3 + 0j)

    def test_bytes(self):
        self.check(b"abc", bytes)

    def test_list(self):
        for modern in False, True:
            with self.subTest(modern=modern):
                List = list if modern else typing.List
                self.assertEqual(self.check([1, 2, 3], List[int]), [1, 2, 3])

    def test_tuple(self):
        for modern in False, True:
            Tuple = tuple if modern else typing.Tuple
            with self.subTest("uniform", modern=modern):
                self.assertEqual(self.check((1, 2, 3), Tuple[int, ...]), [1, 2, 3])
            with self.subTest("pluriform", modern=modern):
                self.assertEqual(
                    self.check((123, "abc"), Tuple[int, str]), [123, "abc"]
                )

    def test_dict(self):
        for modern in False, True:
            with self.subTest(modern=modern):
                Dict = dict if modern else typing.Dict
                self.check({"a": 10, "b": 20}, Dict[str, int]), {"a": 10, "b": 20}

    def test_dataclass(self):
        @dataclass
        class A:
            i: int
            s: str

        self.assertEqual(self.check(A(123, "abc"), A), {"i": 123, "s": "abc"})

    def test_dataclass_defaults(self):
        @dataclass
        class A:
            i: int = 10
            s: str = 20

        with self.assertRaises(ValueError) as cm:
            _mapping.mapping_for(A)
        s = traceback.format_exception(cm.exception)
        self.assertEqual(
            s,
            [
                "ValueError: expects str, got int\n",
                "In: .s(default)\n",
            ]
            if sys.version_info >= (3, 11)
            else [
                "ValueError: expects str, got int\n",
            ],
        )

    def test_boundargs(self):
        def f(i: int, s: str):
            pass

        sig = signature(f)
        bound = sig.bind(123, "abc")
        self.assertEqual(self.check(bound, sig), {"i": 123, "s": "abc"})

    def test_boundargs_defaults(self):
        def f(i: int = 10, s: str = 20):
            pass

        sig = signature(f)
        with self.assertRaises(ValueError) as cm:
            _mapping.mapping_for(sig)
        s = traceback.format_exception(cm.exception)
        self.assertEqual(
            s,
            [
                "ValueError: expects str, got int\n",
                "In: .s(default)\n",
            ]
            if sys.version_info >= (3, 11)
            else [
                "ValueError: expects str, got int\n",
            ],
        )

    def test_union(self):
        for modern in False, True:
            with self.subTest("optional", modern=modern):
                T = int | None if modern else typing.Optional[int]
                self.assertEqual(self.check(123, T), _mapping.OptionalValue(123))
                self.assertEqual(self.check(None, T), _mapping.OptionalValue(None))
            with self.subTest("union", modern=modern):
                T = int | str if modern else typing.Union[int, str]
                self.assertEqual(self.check(123, T), _mapping.UnionValue("int", 123))
                self.assertEqual(
                    self.check("abc", T), _mapping.UnionValue("str", "abc")
                )
            with self.subTest("optional-union", modern=modern):
                T = (
                    int | str | None
                    if modern
                    else typing.Optional[typing.Union[int, str]]
                )
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
                self.assertEqual(self.check(a, A), [2, 3, 4])

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
        self.assertEqual(self.check(a, A), 5)

    def test_exception(self):
        T = dict[str, list[int]]
        m = _mapping.mapping_for(T)
        with self.assertRaises(AssertionError) as cm:
            m.unlower({"a": [10, 20], "b": [30, "40", 50]}, self.mysurject)
        s = traceback.format_exception(cm.exception)
        self.assertEqual(
            s,
            [
                "AssertionError: <class 'str'> is not <class 'int'>\n",
                "In: [b][1]\n",
            ]
            if sys.version_info >= (3, 11)
            else [
                "AssertionError: <class 'str'> is not <class 'int'>\n",
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
    def check_lower(self, obj, expect):
        low = self.mod._inject(obj)
        self.assertEqual(low, expect)
        high = self.mod._surject(low, type(obj))
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


class UCSL(Backend, TestCase):
    from ags import ucsl as mod

    def test_bool(self):
        self.check_lower(True, expect="true")
        self.check_lower(False, expect="false")

    def test_int(self):
        for obj in 0, 1, 2, 10, -5:
            self.check_lower(obj, expect=str(obj))

    def test_float(self):
        for obj in 0.0, 1.0, 2.0, -2.5:
            self.check_lower(obj, expect=str(obj))

    def test_complex(self):
        for obj in 0 + 0j, 1 + 0j, 0 + 1j, -2.5 + 3.5j:
            self.check_lower(obj, expect=str(obj).lstrip("(").rstrip(")"))

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
        self.check_lower(["123", "abc", "xyz"], expect="123,abc,xyz")
        self.check_lower([], expect="")
        self.check_lower(["", ""], expect=",")
        self.check_lower([""], expect="[]")

    def test_dict(self):
        self.check_lower(
            {"a": "123", "b": "abc", "c": "xyz"}, expect="a=123,b=abc,c=xyz"
        )
        self.check_lower({}, expect="")

    def test_union(self):
        self.check_lower(_mapping.UnionValue("abc", "123"), expect="abc[123]")
        self.check_lower(_mapping.UnionValue("abc", ""), expect="abc")

    def test_optional(self):
        self.check_lower(_mapping.OptionalValue("abc"), expect="abc")
        self.check_lower(_mapping.OptionalValue("-"), expect="~-")
        self.check_lower(_mapping.OptionalValue("~-"), expect="~~-")
        self.check_lower(_mapping.OptionalValue("a-z"), expect="a-z")
        self.check_lower(_mapping.OptionalValue(None), expect="-")

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
