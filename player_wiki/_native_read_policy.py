"""Raw recipes for the fixed stock classes used by private read adapters.

These callers run at stock application import, before extension configuration.
Unsupported declarations disable reuse; no descriptor is resolved or unwrapped.
This module is not a class registry or a public provider admission API.
"""
from types import FunctionType, GetSetDescriptorType, MemberDescriptorType


_MISSING = object()


def _capture_class_recipe(cls, *, functions=(), inherited=(), absent=(),
                          getsets=(), slots=False):
    if type(cls) is not type:
        return None
    mro = type.__getattribute__(cls, "__mro__")
    if len(mro) != 2 or mro[0] is not cls or mro[1] is not object:
        return None
    namespace = type.__getattribute__(cls, "__dict__")
    if any(type(name) is not str for name in namespace):
        return None
    entries = []
    for names, kind in ((functions, FunctionType), (getsets, GetSetDescriptorType)):
        for name in names:
            value = namespace.get(name, _MISSING)
            if type(value) is not kind:
                return None
            if (kind is GetSetDescriptorType
                    and (value.__objclass__ is not cls or value.__name__ != name)):
                return None
            entries.append((name, value))
    base = type.__getattribute__(object, "__dict__")
    for names, required_base in ((inherited, True), (absent, False)):
        for name in names:
            if name in namespace or (name in base) is not required_base:
                return None
            entries.append((name, _MISSING))
    if slots:
        names = namespace.get("__slots__", _MISSING)
        if (type(names) is not tuple or len(names) > 64
                or any(type(name) is not str for name in names)):
            return None
        entries.append(("__slots__", names))
        for name in names:
            value = namespace.get(name, _MISSING)
            if (type(value) is not MemberDescriptorType
                    or value.__objclass__ is not cls or value.__name__ != name):
                return None
            entries.append((name, value))
    return cls, mro, tuple(entries)


def _class_recipe_matches(recipe):
    if recipe is None:
        return False
    cls, mro, entries = recipe
    if type(cls) is not type or type.__getattribute__(cls, "__mro__") is not mro:
        return False
    namespace = type.__getattribute__(cls, "__dict__")
    if any(type(name) is not str for name in namespace):
        return False
    return all(namespace.get(name, _MISSING) is value for name, value in entries)
