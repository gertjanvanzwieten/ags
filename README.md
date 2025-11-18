# AGS: Annotation Guided Serialization

The ags module facilitates the serialization and deserialization of arbitrary
Python objects to a supported backend format, currently JSON or YAML. It does
so by recursively lowering the objects into the domain of the backend --
primitive types such as integers, strings and lists -- before passing them on
for serialization. Conversely, after deserialization the primitive types are
converted back from primitive types to the actual objects.

The approach that AGS takes is different from a project such as
[jsonpickle](https://pypi.org/project/jsonpickle/), which employs a bijective
map from the space of arbitrary Python objects to the JSON domain. AGS in
contrast uses a simpler, non-bijective map, aimed at cleaner files that are
suitable for manual editing, at the expense of reversibility.

To restore reversibility, additional information is provided to the serialize
and deserialize operations in the form of type annotations. The thinking here
is that many modern codes already have type annotations in place, so this
information is readily available. For codes that at present lack type
annotations, it is a motivation to go with the times and migrate to static
typing.

Here is a very simple example of AGS in use:

```python
>>> import dataclasses, enum, ags
>>>
>>> class Shape(enum.Enum):
...     square = enum.auto()
...     circle = enum.auto()
>>>
>>> @dataclasses.dataclass
... class MyData:
...     value: complex
...     shape: Shape
>>>
>>> d = MyData(1+2j, Shape.circle)
>>>
>>> ags.dump("data.json", d, MyData)
>>> ags.load("data.json", MyData) == d
True

```

The `dump` and `load` function are passed `MyData` as an additional argument
as there is no annotation to work with for the initial object. From here on,
though, the annotations of the type object are used to guide the recursive map,
resulting in a cast of the complex number to a value dictionary and the enum
object to a string. The generated data.json file is:

```json
{
  "value": {
    "real": 1.0,
    "imag": 2.0
  },
  "shape": "circle"
}
```

The `load` and `dump` functions determine the desired backend based on the file
extension: .json for json and .yml for yaml. These are shorthands for the
functions by the same name in the `ags.json` and `ags.yaml` modules which take
a file-like argument instead. Additionally, these modules provide `loads` and
`dumps` function for serialization to/from a string.

## Supported annotations

The json and yaml formats both support the primitive types `int`, `float`,
`bool` and `str` as well as `list` and `dict` with string valued keys.
Additionally, yaml has support for `date`, `time` and `datetime`.

The following overview lists the conversion rules that are applied to lower
Python objects into this domain based on their type annotation.

- `int`, `float`, `bool`, `str`

  These types are passed through as-is.

- `typing.Literal`

  Literal instances of the above primitive types are also passed through unchanged.

- `complex`

  Complex numbers are not natively supported by either JSON or YAML. Numbers
  without an imaginary part are converted to a float, the rest to a dictionary
  with keys 'real' and 'imag' and floating point values.

- `bytes`

  Bytes are not natively supported by either JSON or YAML, and are converted to
  a base85 encoded string. Alternatively, if the bytes sequence matches an
  encoded unicode string, then this string prefixed with the encoding and a
  colon (like utf8:) is also valid (the colon is excluded from the base85
  character set).

- `typing.Optional`

  Optional data is returned as None or the converted non-optional value.

- `typing.Union`

  Unions of multiple types are converted to a single item dictionary, where the
  key is the name of the type and the value the converted object.

  Here we run into an issue if any of the options has no `__name__` attribute,
  or its value is not descriptive enough ("int", "str") for the purposes of a
  data format. This can be solved by annotating the type, e.g,
  `typing.Annotated[int, "amount"]`. Note that while this convention is AGS
  specific, annotations of this type can be added freely and do not interfere
  with static type checkers.

  Note that unions are the main reason that type annotations must be provided
  to the `dump` function, as without it the mapping would be strictly
  injective from object space.

- `list`, `tuple`

  Lists and tuples are converted to lists of their converted items. Item type
  annotations (e.g. `list[int]`) are required. Both uniform tuples (`tuple[int,
  ...]`) and fixed length tuples (`tuple[int, str]`) are supported.

- `dict`

  Dictionaries are converted to dictionaries with their values converted; only
  string valued keys are supported for now. Annotations for both key and value
  are mandatory.

- `dataclasses.dataclass`

  Data classes are converted to dictionaries based on their attribute
  annotations.

- `datetime.date`, `datetime.time`, `datetime.datetime`

  Date objects are natively supported by YAML and returned as-is. For JSON they
  are converted to a string in ISO 8601 format.

- `enum.Enum`

  Enum objects are identified by their name.

- `inspect.Signature`

  A function signature will not generally be used as a type annotation, but it
  is supported for dumping and loading of an `inspect.BoundArguments` instance.
  This is a convenient way of converting all arguments of a function to and
  from a dictionary.

- objects that reduce to a single constructor argument

  Lastly, objects that reduce to their own class and a single argument are
  identified by that argument.

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

  The particular return annotation for the `__reduce__` method is required for
  AGS to recognize this structure.
