from dataclasses import dataclass
from enum import Enum
from inspect import signature
from typing import Union, Literal, Tuple, List, Dict, Optional, Self, Type
from unittest import TestCase
from io import StringIO
from datetime import datetime
from doctest import DocTestSuite, DocFileSuite

from ags._mapping import mapping_for


def load_tests(loader, tests, ignore):
    tests.addTests(DocFileSuite("README.md"))
    return tests


class Mapping(TestCase):
    def check(self, obj, T):
        m = mapping_for(T, "", with_date=False)
        low = m.lower(obj, "")
        high = m.unlower(low, "")
        self.assertEqual(high, obj)
        return low

    def test_primitive(self):
        for obj in "abc", 123, 1.5, True, False, None:
            T = type(obj)
            with self.subTest(T.__name__):
                self.assertEqual(self.check(obj, T), obj)

    def test_literal(self):
        T = Literal["abc", 123]
        for obj in "abc", 123:
            self.assertEqual(self.check(obj, T), obj)

    def test_complex(self):
        self.assertEqual(self.check(1 + 2j, complex), dict(real=1.0, imag=2.0))
        self.assertEqual(self.check(3 + 0j, complex), 3.0)

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
        for name in "optional", "union", "optional-union":
            is_union = name.endswith("union")
            is_optional = name.startswith("optional")
            with self.subTest(name):
                T = int
                if is_union:
                    T = Union[T, str]
                if is_optional:
                    T = Optional[T]
                    self.assertEqual(self.check(None, T), None)
                v = self.check(123, T)
                if is_union:
                    self.assertEqual(v, {"int": 123})
                    self.assertEqual(self.check("abc", T), {"str": "abc"})
                else:
                    self.assertEqual(v, 123)

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


class Test(TestCase):
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

    def setUp(self):
        cls = type(self)
        a = cls.A(1, 2.5)
        b = [cls.B("a", cls.B.Sub(b"foo", "αβγ")), cls.B("b", cls.B.Sub(b"bar", None))]
        direction = cls.Right(datetime.fromtimestamp(1753600000))
        self.sig = signature(cls.func)
        self.bound = self.sig.bind(a, b, direction)

    def test_load(self):
        obj = self.mod.load(StringIO(self.expect), self.sig)
        self.assertEqual(obj, self.bound)

    def test_loads(self):
        obj = self.mod.loads(self.expect, self.sig)
        self.assertEqual(obj, self.bound)

    def test_dump(self):
        f = StringIO()
        self.mod.dump(f, self.bound, self.sig)
        self.assertEqual(f.getvalue(), self.expect)

    def test_dumps(self):
        s = self.mod.dumps(self.bound, self.sig)
        self.assertEqual(s, self.expect)


class Json(Test):
    from ags import json as mod

    expect = """\
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
"""


class Yaml(Test):
    from ags import yaml as mod

    expect = """\
a:
  x: 1
  y: 2.5
b:
- abc: a
  sub:
    b: utf8:foo
    greek: αβγ
- abc: b
  sub:
    b: utf8:bar
    greek: null
direction:
  Right:
    when: 2025-07-27 09:06:40
"""


del Test
