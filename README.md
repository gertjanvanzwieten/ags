# AGS: Annotation Guided Serialization

The ags module facilitates the serialization and deserialization of arbitrary
Python objects to a supported backend format, currently JSON, YAML, and the
home grown UCSL. It does so by recursively lowering the objects into the domain
of the backend -- primitive types such as integers, strings and lists -- before
passing them on for serialization. Conversely, after deserialization the
primitive types are converted back from primitive types to the actual objects.

The approach that AGS takes is different from a project such as
[jsonpickle](https://pypi.org/project/jsonpickle/), which employs a bijective
map from the space of arbitrary Python objects to the JSON domain. AGS in
contrast applies a simpler, non-bijective map, aimed at cleaner files that are
suitable for manual editing, at the expense of reversibility.

To restore reversibility, additional information is provided to the serialize
and deserialize operations in the form of type annotations. The thinking here
is that many modern codes already have type annotations in place, so this
information is readily available. For codes that at present lack type
annotations, it is a motivation to go with the times and migrate to static
typing.

Here is a simple example of AGS in use, featuring some data types that would
ordinarily trip up a JSON or YAML engine:

```python
>>> import dataclasses, enum, ags
>>>
>>> @dataclasses.dataclass
... class Point:
...     value: complex
...     end: float|None = None
>>>
>>> class Axis(enum.Enum):
...     real = 1
...     imag = 2
>>>
>>> L = list[Point|Axis]
>>> items: L = [Point(1+2j), Axis.real, Point(1j,1.5)]
>>>
>>> ags.dump("data.yml", items, L)
>>> ags.load("data.yml", L) == items
True

```

The `dump` and `load` function are passed `L`, as the `items` object does not
carry its own annotation. From here on the annotations of the type object are
used to guide the recursive map, resulting in a cast of both the union and
dataclasses to dictionaries. The generated data.yml file is:

```yaml
- Point:
    value: 1+2j
    end: null
- Axis: real
- Point:
    value: 1j
    end: 1.5
```

The desired serialization backend is based on the file extension: .json for
json and .yml for yaml. Alternatively there are `dump` and `load` functions in
the relevant submodules (`ags.json` and `ags.yaml`) that take a file-like
argument instead. These modules also provide `dumps` and `loads` functions for
serialization to/from a string.

## Operation

AGS serialization consists of three steps:

### Step 1: Lower Python objects to AGS primitives.

Python objects with a supported type annotation get recursively converted
("lowered") to one of a finite set of AGS primitives. The list of AGS
primitives is: boolean, integer, float, complex, string, bytes, list,
dictionary, date, time, datetime, a primitive for `Optional` annotations and a
primitive for `Union` annotations.

These are the Python type annotations that are currently supported, and the AGS
primitives that they are converted into. Note that these choices are common to
all the backends that follow.

- `int`, `float`, `bool`, `complex`, `str`, `bytes`, `date`, `time`, `datetime`

  These types are passed through as-is.

- `typing.Literal`

  Literal instances of the above primitive types are also passed through unchanged.

- `typing.Optional` or `T|None`

  Optional data is returned as the optional primitive.

- `typing.Union` or `T1|T2|T3`

  Unions of multiple types are lowered to a union primitive holding the name
  of the type and the value the lowered object.

  Here we run into an issue if any of the options has no `__name__` attribute,
  or its value is not descriptive enough ("int", "str") for the purposes of a
  data format. This can be solved by annotating the type, e.g,
  `typing.Annotated[int, "amount"]`. Note that while this convention is AGS
  specific (something we aim to avoid), annotations of this type can be added
  freely and do not interfere with static type checkers.

  Note that unions are the main reason that type annotations must be provided
  to the `dump` function, as without it the mapping would be strictly
  injective from object space.

- `list`, `tuple`

  Lists and tuples are lowered to lists of their lowered items. Item type
  annotations (e.g. `list[int]`) are required. Both uniform tuples (`tuple[int,
  ...]`) and fixed length tuples (`tuple[int, str]`) are supported.

- `dict`

  Dictionaries are lowered to dictionaries with their keys and values
  lowered. Annotations for both key and value are mandatory.

- `dataclasses.dataclass`

  Data classes are lowered to dictionaries based on their attribute
  annotations.

- `enum.Enum`

  Enum objects are identified by their name and lowered to a string.

- `inspect.Signature`

  A function signature will not generally be used as a type annotation, but it
  is supported for dumping and loading of an `inspect.BoundArguments` instance.
  This is a convenient way of lowering all arguments of a function to and
  from a dictionary.

- objects that define `__into_ags__` and `__from_ags__`

  Any object can make itself suitable for AGS by defining two special methods
  that transform the object into and out of an alternative form which AGS does
  know how to handle. Here is an example of a custom class that is serilialized
  as a string:

  ```python
  >>> from typing import Self
  >>>
  >>> class MyClass:
  ...     def __init__(self, s: str):
  ...         self.s = s
  ...     def __into_ags__(self) -> str:
  ...         return self.s
  ...     @classmethod
  ...     def __from_ags__(cls, s: str):
  ...         return cls(self.s)
  >>>
  >>> ags.json.dumps(MyClass("foo"), MyClass)
  '"foo"\n'

  ```

- objects that reduce to a single constructor argument (Python >= 3.11)

  Lastly, objects that reduce to their own class and a single argument are
  identified by that argument. This is very similar to the `__into_ags__`
  method except that this also affects the way the object is pickled. It also
  requires a particular annotation for AGS to recognize the pattern, which is
  only avaliable as of Python 3.11:

  ```python
  >>> from typing import Self
  >>>
  >>> class MyClass:
  ...     def __init__(self, s: str):
  ...         self.s = s
  ...     def __reduce__(self) -> tuple[type[Self], tuple[str]]:
  ...         return MyClass, (self.s,)
  >>>
  >>> ags.json.dumps(MyClass("foo"), MyClass)
  '"foo"\n'

  ```

### Step 2: Lower AGS primitives to the domain of the backend

Different backends support different data types. For instance, YAML supports
date objects whereas JSON does not. Depending on the selected backend the
object resulting from step 1 therefore needs to be lowered further in a
preprocessing step before it can be passed on to the serialisation routine.

Here we list the conversion choices that AGS makes for each of the supported
backends.

#### JSON

The JavaScript Object Notation file format defines the primitives number,
string, boolean, array of primitives, a mapping from a string to a primitive,
and null.

- integer, float, boolean, string, list, dictionary

  These types are passed through as-is.

- complex

  Complex numbers without an imaginary part are converted to a float, the rest
  to a string in Python notation (e.g. 1+2j).

- bytes

  Bytes are converted to a base85 encoded string. Alternatively, if the bytes
  sequence matches an encoded unicode string, then this string prefixed with
  the encoding and a colon (like utf8:) is also valid (the colon is excluded
  from the base85 character set).

- optional

  Optional values are returned as either the value or null.

- union

  Unions of multiple types are converted to a single item dictionary, where the
  key is the name of the type and the value the object.

- date, time, datetime

  Date objects are converted to a string in ISO 8601 format.

#### YAML

The YAML Ain’t Markup Language is a superset of JSON as of version 1.2, which
means a JSON file is valid YAML, but not any YAML file is valid JSON. YAML
notably adds the date and binary primitives, which AGS supports by passing
them unchanged.

- integer, float, boolean, string, list, dictionary, bytes, date, time, datetime

  These types are passed through as-is.

- complex

  Complex numbers without an imaginary part are converted to a float, the rest
  to a string in Python notation (e.g. 1+2j).

- optional

  Optional values are returned as either the value or null.

- union

  Unions of multiple types are converted to a single item dictionary, where the
  key is the name of the type and the value the object.

#### UCSL

The Ultra Compact Serialisation Language is a custom language specifically
designed for the AGS concept. This is an evolution of the
[stringly](https://github.com/evalf/stringly) project, which used a different
notation but otherwise similar concepts. It's primary use case is command line
arguments and environment variables.

UCSL has only the string primitive, and relies entirely on type annotations for
interpretation. This means the string 123 can either be a string, an integer, a
float, a complex number, or even a single item list of any of the above. There
are no special characters to be escaped, but nested structures may be enclosed
in square brackets to distinguish inner and outer separation characters.

- integer, float, complex, string

  These types are converted according to the Python string representation.

- boolean

  Boolean values are converted to the strings "true" or "false", lowercase,
  even though the capitalized versions and also "yes" and "no" are all
  supported in deserialization.

- list

  List items are comma joined. Any item that contains a comma in lowered form
  is enclosed in square brackets.

  ```python
  >>> ags.ucsl.dumps([["foo"], ["bar", "baz"]], list[list[str]])
  'foo,[bar,baz]'

  ```

  Note that, while `dumps` introduces the minimum amount of brackets, `loads`
  accepts them wherever they may occur, even if they are not required.

  ```python
  >>> ags.ucsl.loads("[foo],[bar,baz]", list[list[str]])
  [['foo'], ['bar', 'baz']]

  ```

- dictionary

  Dictionary items are comma joined, and the key and value equals joined. Any
  key that contains a comma or equals is enclosed in square brackets; so is any
  value that contains a comma.

  ```python
  >>> ags.ucsl.dumps({"a=>z": [123], "foo": [4, 5]}, dict[str,list[int]])
  '[a=>z]=123,foo=[4,5]'

  ```

- bytes

  Bytes are converted to a base85 encoded string. Alternatively, if the bytes
  sequence matches an encoded unicode string, then this string prefixed with
  the encoding and a colon (like utf8:) is also valid (the colon is excluded
  from the base85 character set).

- optional

  An undefined optional value is represented by a single dash (-). Defined
  optional values are enclosed in brackets only if they lower to a dash.

- union

  Unions of multiple types are converted to the name of the type followed by
  the object enclosed in square brackets. E.g., from the introduction:

  ```python
  >>> ags.ucsl.dumps(items, L)
  'Point[value=1+2j,end=-],Axis[real],Point[value=1j,end=1.5]'

  ```

- date, time, datetime

  Date objects are converted to a string in ISO 8601 format.

### Step 3: Serialization

This is simply a matter of passing on the lowered object to the relevant
serialization routine. Note that the JSON routines are part of Python's
included batteries, whereas YAML requires installation of the external PyYAML
module. The UCSL backend doesn't require serialization as its preprocessor
already lowers everything down to a string.

Finally, deserialization consists of running to inverse operations of the three
steps in opposite order.
