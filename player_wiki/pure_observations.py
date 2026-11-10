"""Bounded pure YAML content, separate from every live source/access proof.

Only the fixed stock parser is admitted. Cache entries contain immutable plain
data; each consumer receives a new tree. No database, actor or authority value
is retained. Small inputs keep the ordinary parser to avoid recipe-check cost.
"""
from collections import OrderedDict
from datetime import date
import math
import re
import sys
import base64
import binascii
import collections.abc
import _collections_abc
import _abc
import abc
import builtins
import codecs
import types
import datetime as dates
import collections.abc as collections_abc
from abc import ABCMeta
from threading import Lock
from types import (BuiltinFunctionType, CodeType, FunctionType, ModuleType,
                   GetSetDescriptorType, MethodDescriptorType, CellType)

import yaml
from yaml import (composer, constructor, error, events, loader, nodes, parser,
                  reader, resolver, scanner, tokens)


_MIN_INPUT = 1024
_MAX_INPUT = 256 * 1024
_MAX_BYTES = 16 * 1024 * 1024
_MAX_ENTRIES = 512
_MAX_NODES = 32768
_MAX_DEPTH = 64
_MISSING = object()
_PATTERN = None
_STOCK_PARSE = None
_NATIVE_GETSIZE = None
_NATIVE_ISFINITE = None
_MODULE_DICT = None
_TYPE_FIELDS = {name: vars(type)[name] for name in (
    "__dict__", "__module__", "__name__", "__qualname__", "__mro__", "__bases__", "__flags__")}
_TYPE_NAMESPACE_KIND = type(vars(type))


def _module_namespace(module):
    global _MODULE_DICT
    if type(module) is not ModuleType:
        raise ValueError("Configured module protocol")
    if _MODULE_DICT is None:
        if type(ModuleType) is not type:
            raise ValueError("Configured module kind")
        declaration = _type_field(ModuleType, "__dict__")
        if any(type(name) is not str for name in declaration):
            raise ValueError("Configured module kind namespace")
        descriptor = declaration.get("__dict__")
        if (type(descriptor) is not type(_TYPE_FIELDS["__flags__"])
                or descriptor.__objclass__ is not ModuleType):
            raise ValueError("Configured module storage")
        _MODULE_DICT = descriptor
    namespace = _MODULE_DICT.__get__(module, ModuleType)
    if type(namespace) is not dict or len(namespace) > 32768:
        raise ValueError("Unbounded module namespace")
    return namespace


def _type_field(cls, name):
    # Invoke the original C type descriptor directly. type.__getattribute__
    # alone can still bind data descriptors installed on a metaclass.
    if type(name) is not str:
        raise ValueError("Configured type field name")
    value = _TYPE_FIELDS[name].__get__(cls, type(cls))
    if name in ("__mro__", "__bases__") and type(value) is not tuple:
        raise ValueError("Configured type ancestry container")
    if name == "__dict__" and (type(value) is not _TYPE_NAMESPACE_KIND or len(value) > 32768):
        raise ValueError("Unbounded class namespace")
    return value


def _code_metadata(root):
    seen = set()
    remaining = 32768
    def visit(value, depth=0):
        nonlocal remaining
        remaining -= 1
        if remaining < 0:
            raise ValueError("Unbounded code metadata visits")
        identity, kind = id(value), type(value)
        if identity in seen:
            return
        seen.add(identity)
        if len(seen) > 32768 or depth > 64:
            raise ValueError("Unbounded code metadata")
        if kind is CodeType:
            if any(type(item) is not str for item in (
                    value.co_name, value.co_qualname, value.co_filename)):
                raise ValueError("Configured code scalar")
            if value.co_filename != root.co_filename:
                raise ValueError("Configured nested code origin")
            for names in (value.co_names, value.co_varnames, value.co_freevars, value.co_cellvars):
                if type(names) is not tuple or len(names) > remaining:
                    raise ValueError("Configured code name container")
                remaining -= len(names)
                if any(type(name) is not str for name in names):
                    raise ValueError("Configured code names")
            if type(value.co_consts) is not tuple:
                raise ValueError("Configured code constant container")
            visit(value.co_consts, depth + 1)
        elif kind is tuple or kind is frozenset:
            if len(value) > remaining:
                raise ValueError("Unbounded code constant width")
            for child in value:
                visit(child, depth + 1)
        elif not any(kind is scalar for scalar in (
                type(None), bool, int, float, complex, str, bytes)) and value is not Ellipsis:
            raise ValueError("Configured code constant leaf")
    visit(root)



def _function_code(value):
    if type(value) is not FunctionType:
        raise ValueError("Configured YAML function")
    if type(value.__globals__) is not dict:
        raise ValueError("Configured function globals")
    closure = value.__closure__
    if closure is not None and (type(closure) is not tuple or len(closure) > 32768
            or any(type(cell) is not CellType for cell in closure)):
        raise ValueError("Configured function closure")
    code = value.__code__
    if any(type(item) is not str for item in (value.__module__, value.__name__,
            value.__qualname__, code.co_name, code.co_qualname, code.co_filename)):
        raise ValueError("Configured YAML function metadata")
    _code_metadata(code)
    return code


def _fixed_stock_loader():
    """Refuse configured loader aliases before resolving any of their hooks."""
    modules = (yaml, loader, reader, scanner, parser, composer, constructor, resolver)
    if any(type(module) is not ModuleType for module in modules):
        return False
    if any(any(type(name) is not str for name in _module_namespace(module)) for module in modules):
        return False
    for module, expected_name in zip(modules, (
            "yaml", "yaml.loader", "yaml.reader", "yaml.scanner", "yaml.parser",
            "yaml.composer", "yaml.constructor", "yaml.resolver")):
        module_name = _module_namespace(module).get("__name__")
        if type(module_name) is not str or module_name != expected_name:
            return False
    native = _module_namespace(loader).get("SafeLoader")
    if type(native) is not type or _module_namespace(yaml).get("SafeLoader") is not native:
        return False
    bases = tuple(_module_namespace(module).get(name) for module, name in (
        (reader, "Reader"), (scanner, "Scanner"), (parser, "Parser"),
        (composer, "Composer"), (constructor, "SafeConstructor"), (resolver, "Resolver")))
    if any(type(base) is not type for base in bases):
        return False
    for module, name, expected_bases in (
            (reader, "Reader", (object,)), (scanner, "Scanner", (object,)),
            (parser, "Parser", (object,)), (composer, "Composer", (object,)),
            (constructor, "BaseConstructor", (object,)),
            (constructor, "SafeConstructor", (_module_namespace(constructor).get("BaseConstructor"),)),
            (resolver, "BaseResolver", (object,)),
            (resolver, "Resolver", (_module_namespace(resolver).get("BaseResolver"),))):
        base = _module_namespace(module).get(name)
        if type(base) is not type:
            return False
        declaration = _type_field(base, "__dict__")
        if any(type(key) is not str for key in declaration):
            return False
        module_name, qualified_name = declaration.get("__module__"), _type_field(base, "__qualname__")
        actual = _type_field(base, "__bases__")
        if (type(module_name) is not str or type(qualified_name) is not str
                or module_name != _module_namespace(module).get("__name__") or qualified_name != name
                or len(actual) != len(expected_bases)
                or any(a is not b for a, b in zip(actual, expected_bases))):
            return False
    actual_bases = _type_field(native, "__bases__")
    expected_mro = (native, *bases[:5], _module_namespace(constructor).get("BaseConstructor"),
                    bases[5], _module_namespace(resolver).get("BaseResolver"), object)
    actual_mro = _type_field(native, "__mro__")
    if (len(actual_bases) != len(bases) or any(a is not b for a, b in zip(actual_bases, bases))
            or len(actual_mro) != len(expected_mro)
            or any(a is not b for a, b in zip(actual_mro, expected_mro))):
        return False
    namespace = _type_field(native, "__dict__")
    if any(type(name) is not str for name in namespace):
        return False
    module_name, qualified_name = namespace.get("__module__"), _type_field(native, "__qualname__")
    if (len(namespace) != 3
            or type(module_name) is not str or type(qualified_name) is not str
            or module_name != "yaml.loader" or qualified_name != "SafeLoader"
            or namespace.get("__doc__") is not None):
        return False
    initialize = namespace.get("__init__")
    if type(initialize) is not FunctionType:
        return False
    code = _function_code(initialize)
    return (type(initialize.__module__) is str
            and type(_module_namespace(loader).get("__file__")) is str
            and initialize.__module__ == "yaml.loader"
            and initialize.__qualname__ == "SafeLoader.__init__"
            and initialize.__globals__ is _module_namespace(loader)
            and code.co_filename == _module_namespace(loader).get("__file__")
            and initialize.__defaults__ is None and initialize.__kwdefaults__ is None
            and initialize.__closure__ is None)


class _StockYamlRecipe:
    """A fixed comparison plan, captured before application configuration.

    This is not a registry for arbitrary providers. Raw YAML class/module
    declarations and the globals actually referenced by their Python code are
    inspected without resolving descriptors.
    """

    def __init__(self):
        global _PATTERN, _STOCK_PARSE, _NATIVE_GETSIZE, _NATIVE_ISFINITE
        literal = lambda: None
        cell = (lambda value: lambda: value)(None).__closure__[0]
        if (FunctionType is not type(literal) or CodeType is not type(literal.__code__)
                or CellType is not type(cell)
                or BuiltinFunctionType is not type(vars(type)["__new__"])
                or GetSetDescriptorType is not type(_TYPE_FIELDS["__dict__"])
                or MethodDescriptorType is not type(type("").join)):
            raise ValueError("Configured native kind aliases")
        # Every dependency is admitted raw before any of its attributes/hooks
        # participate in construction. This is a closed stock graph, not a
        # registry for configured providers.
        yaml_modules = (loader, reader, scanner, parser, composer, constructor,
                        resolver, nodes, tokens, events, error)
        fixed = ((yaml, "yaml"), *zip(yaml_modules, (
            "yaml.loader", "yaml.reader", "yaml.scanner", "yaml.parser",
            "yaml.composer", "yaml.constructor", "yaml.resolver", "yaml.nodes",
            "yaml.tokens", "yaml.events", "yaml.error")),
            (dates, "datetime"), (collections, "collections"),
            (collections_abc, "collections.abc"), (_collections_abc, "collections.abc"),
            (abc, "abc"), (_abc, "_abc"), (base64, "base64"),
            (binascii, "binascii"), (re, "re"), (codecs, "codecs"),
            (sys, "sys"), (types, "types"), (builtins, "builtins"), (math, "math"))
        for module, name in fixed:
            if type(module) is not ModuleType:
                raise ValueError("Configured YAML dependency")
            namespace = _module_namespace(module)
            if any(type(key) is not str for key in namespace):
                raise ValueError("Configured dependency keys")
            actual = namespace.get("__name__")
            if type(actual) is not str or actual != name:
                raise ValueError("Configured dependency name")
        self.modules = tuple(module for module, _name in fixed)
        self.namespaces, self.functions, self.containers = [], [], []
        self.bindings, self.classes, self.key_namespaces = [], [], []
        for module, _name in fixed:
            namespace = _module_namespace(module)
            self.key_namespaces.append(namespace)
            for name in ("__name__", "__file__"):
                self.bindings.append((namespace, name, namespace.get(name, _MISSING)))
        for module, name in ((sys, "getsizeof"), (math, "isfinite")):
            function = _module_namespace(module).get(name)
            if (type(function) is not BuiltinFunctionType
                    or type(function.__module__) is not str or type(function.__name__) is not str
                    or function.__module__ != _module_namespace(module)["__name__"] or function.__name__ != name
                    or function.__self__ is not module):
                raise ValueError("Configured pure representation helper")
            self.bindings.append((_module_namespace(module), name, function))
        _NATIVE_GETSIZE, _NATIVE_ISFINITE = _module_namespace(sys)["getsizeof"], _module_namespace(math)["isfinite"]
        seen = set()
        remaining = 32768

        def same_types(actual, expected):
            return len(actual) == len(expected) and all(a is b for a, b in zip(actual, expected))

        def namespace_keys(namespace):
            if not any(namespace is previous for previous in self.key_namespaces):
                if any(type(name) is not str for name in namespace):
                    raise ValueError("Configured YAML namespace")
                self.key_namespaces.append(namespace)

        def class_metadata(cls, module_name, name):
            if type(cls) is not type and type(cls) is not ABCMeta:
                raise ValueError("Configured YAML class protocol")
            namespace = _type_field(cls, "__dict__")
            namespace_keys(namespace)
            metadata = (_type_field(cls, "__module__"),
                        _type_field(cls, "__name__"),
                        _type_field(cls, "__qualname__"))
            if any(type(value) is not str for value in metadata):
                raise ValueError("Configured class metadata")
            if metadata != (module_name, name, name):
                raise ValueError("Configured native class")
            return namespace

        # Fixed native dependency declarations, without binding descriptors.
        if _module_namespace(abc).get("ABCMeta") is not ABCMeta:
            raise ValueError("Configured ABC alias")
        abc_namespace = class_metadata(ABCMeta, "abc", "ABCMeta")
        if not same_types(_type_field(ABCMeta, "__mro__"), (ABCMeta, type, object)):
            raise ValueError("Configured ABC ancestry")
        if _module_namespace(collections).get("abc") is not collections_abc:
            raise ValueError("Configured collections alias")
        hashable = _module_namespace(collections_abc).get("Hashable")
        if type(hashable) is not ABCMeta:
            raise ValueError("Configured Hashable")
        hash_namespace = class_metadata(hashable, "collections.abc", "Hashable")
        if not same_types(_type_field(hashable, "__mro__"), (hashable, object)):
            raise ValueError("Configured Hashable ancestry")

        pattern = _module_namespace(re).get("Pattern")
        pattern_namespace = class_metadata(pattern, "re", "Pattern")
        pattern_match = pattern_namespace.get("match")
        if (type(pattern_match) is not MethodDescriptorType
                or pattern_match.__objclass__ is not pattern):
            raise ValueError("Configured native pattern type")
        _PATTERN = pattern

        storage = hash_namespace.get("_abc_impl")
        storage_kind = type(storage)
        storage_namespace = class_metadata(storage_kind, "_abc", "_abc_data")
        storage_new = storage_namespace.get("__new__")
        if (len(storage_namespace) != 3 or type(storage_new) is not BuiltinFunctionType
                or storage_new.__self__ is not storage_kind
                or not same_types(_type_field(storage_kind, "__bases__"), (object,))):
            raise ValueError("Configured ABC storage")

        temporal = []
        for name in ("date", "datetime", "timedelta", "timezone"):
            cls = _module_namespace(dates).get(name)
            declaration = class_metadata(cls, "datetime", name)
            new = declaration.get("__new__")
            if type(new) is not BuiltinFunctionType or new.__self__ is not cls:
                raise ValueError("Configured temporal constructor")
            temporal.append(cls)
        binary_error = _module_namespace(binascii).get("Error")
        error_namespace = class_metadata(binary_error, "binascii", "Error")
        if (len(error_namespace) != 3
                or not same_types(_type_field(binary_error, "__bases__"), (ValueError,))):
            raise ValueError("Configured decoder error")

        # Function metadata is validated before comparing/hashing any string.
        for name in ("safe_load", "load"):
            function = _module_namespace(yaml).get(name)
            code = _function_code(function)
            if (function.__module__ != "yaml" or function.__globals__ is not _module_namespace(yaml)
                    or function.__name__ != name or function.__qualname__ != name
                    or code.co_name != name):
                raise ValueError("Configured YAML entrypoint")
        if not _fixed_stock_loader():
            raise ValueError("Configured YAML loader")
        _STOCK_PARSE = _module_namespace(yaml)["safe_load"]

        hooks = []
        for module, name in ((base64, "decodebytes"), (base64, "_input_type_check"),
                              (_collections_abc, "_check_methods")):
            function = _module_namespace(module).get(name)
            _function_code(function)
            if function.__globals__ is not _module_namespace(module):
                raise ValueError("Configured parser helper")
            hooks.append((function, module))
        subclass_hook = hash_namespace.get("__subclasshook__")
        if type(subclass_hook) is not classmethod:
            raise ValueError("Configured Hashable hook")
        hooks.append((object.__getattribute__(subclass_hook, "__func__"), _collections_abc))
        for name in ("__instancecheck__", "__subclasscheck__"):
            hooks.append((abc_namespace.get(name), abc))
        for function, owner in hooks:
            _function_code(function)
            if function.__globals__ is not _module_namespace(owner):
                raise ValueError("Configured parser helper globals")
        external_functions = tuple(function for function, _owner in hooks)

        classes = []
        allowed = {_module_namespace(module)["__name__"]: module for module in yaml_modules}
        for module in yaml_modules:
            namespace = _module_namespace(module)
            entries = tuple((name, value) for name, value in namespace.items()
                            if not name.startswith("__"))
            self.namespaces.append((namespace, entries, False))
            for name, value in entries:
                if type(value) is type:
                    origin = _type_field(value, "__module__")
                    if type(origin) is not str:
                        raise ValueError("Configured class origin")
                    if origin == _module_namespace(module)["__name__"]:
                        class_metadata(value, origin, name)
                        if not any(value is previous for previous in classes):
                            classes.append(value)
        classes.extend((hashable, ABCMeta))
        external_classes = tuple(temporal) + (binary_error,)
        native_builtin_functions = tuple(value for name, value in _module_namespace(builtins).items()
            if type(value) is BuiltinFunctionType
            and type(value.__module__) is str and type(value.__name__) is str
            and value.__module__ == "builtins" and value.__name__ == name)
        native_c_functions = []
        for module, name in ((_abc, "_abc_instancecheck"), (_abc, "_abc_subclasscheck"),
                             (binascii, "a2b_base64")):
            function = _module_namespace(module).get(name)
            if (type(function) is not BuiltinFunctionType
                    or type(function.__module__) is not str or type(function.__name__) is not str
                    or function.__module__ != _module_namespace(module)["__name__"] or function.__name__ != name):
                raise ValueError("Configured native helper")
            native_c_functions.append(function)

        native_getsets = []
        for cls in classes:
            declaration = _type_field(cls, "__dict__")
            namespace_keys(declaration)
            for name in ("__dict__", "__weakref__"):
                value = declaration.get(name)
                if value is not None:
                    if (type(value) is not GetSetDescriptorType
                            or value.__objclass__ is not cls or type(value.__name__) is not str
                            or value.__name__ != name):
                        raise ValueError("Configured class descriptor")
                    native_getsets.append(value)

        def native_class(value):
            if any(value is cls for cls in (*classes, *external_classes)):
                return True
            if type(value) is not type:
                return False
            origin = _type_field(value, "__module__")
            name = _type_field(value, "__name__")
            return (type(origin) is str and type(name) is str and origin == "builtins"
                    and _module_namespace(builtins).get(name) is value)

        def capture(value):
            nonlocal remaining
            remaining -= 1
            if remaining < 0:
                raise ValueError("Unbounded recipe visits")
            kind = type(value)
            identity = id(value)
            if identity in seen:
                return
            seen.add(identity)
            if len(seen) > 32768:
                raise ValueError("Unbounded YAML recipe")
            if (value is _MISSING or value is NotImplemented or value is storage
                    or any(kind is scalar for scalar in (type(None), bool, int, float, str, bytes))):
                return
            if kind is FunctionType:
                code = _function_code(value)
                namespace = value.__globals__
                namespace_keys(namespace)
                owner = next((module for module in (yaml, *yaml_modules)
                              if _module_namespace(module) is namespace), None)
                if owner is None:
                    owner = next((module for function, module in hooks if function is value), None)
                if owner is None:
                    raise ValueError("Configured YAML callback")
                filename = _module_namespace(owner).get("__file__")
                if type(filename) is not str:
                    raise ValueError("Configured callback source")
                if code.co_filename != filename and not (
                        owner is abc and code.co_filename == "<frozen abc>" or
                        owner is _collections_abc and code.co_filename == "<frozen _collections_abc>"):
                    raise ValueError("Configured callback code")
                defaults, keywords, closure = value.__defaults__, value.__kwdefaults__, value.__closure__
                self.functions.append((value, code, defaults, keywords, closure))
                capture(defaults); capture(keywords)
                if closure:
                    for cell in closure:
                        child = cell.cell_contents
                        self.bindings.append((cell, None, child))
                        capture(child)
                names, pending, code_count = set(), [code], 0
                while pending:
                    current = pending.pop()
                    code_count += 1
                    if (type(current.co_names) is not tuple or type(current.co_consts) is not tuple
                            or code_count > 4096 or len(current.co_names) > 32768
                            or any(type(name) is not str for name in current.co_names)):
                        raise ValueError("Configured code names")
                    names.update(current.co_names)
                    pending.extend(child for child in current.co_consts if type(child) is CodeType)
                builtin_namespace = value.__builtins__
                if type(builtin_namespace) is not dict:
                    raise ValueError("Configured callback builtins")
                namespace_keys(builtin_namespace)
                for name in names:
                    actual = namespace.get(name, _MISSING)
                    self.bindings.append((namespace, name, actual))
                    if actual is _MISSING:
                        actual = builtin_namespace.get(name, _MISSING)
                        self.bindings.append((builtin_namespace, name, actual))
                    elif (name in _module_namespace(builtins)
                            and (type(_module_namespace(builtins)[name]) is type
                                 or type(_module_namespace(builtins)[name]) is BuiltinFunctionType)
                            and actual is not _module_namespace(builtins)[name]):
                        raise ValueError("Configured builtin shadow: " + name)
                    capture(actual)
            elif kind is dict:
                if len(value) > remaining // 2:
                    raise ValueError("Unbounded recipe mapping")
                entries = tuple(value.items())
                if any(not any(type(key) is scalar for scalar in (str, type(None), int))
                       for key, _child in entries):
                    raise ValueError("Configured recipe keys")
                self.containers.append((value, entries, True))
                for key, child in entries:
                    capture(key)
                    capture(child)
            elif kind is list or kind is tuple or kind is frozenset:
                if len(value) > remaining:
                    raise ValueError("Unbounded recipe sequence")
                children = tuple(value)
                self.containers.append((value, children, False))
                for child in children:
                    capture(child)
            elif kind is staticmethod or kind is classmethod:
                capture(object.__getattribute__(value, "__func__"))
            elif kind is _PATTERN:
                pattern_text, flags = value.pattern, value.flags
                if type(pattern_text) is not str or type(flags) is not int:
                    raise ValueError("Configured pattern metadata")
                self.bindings.extend(((value, "pattern", pattern_text), (value, "flags", flags)))
            elif kind is ModuleType:
                if not any(value is module for module in self.modules):
                    raise ValueError("Configured module leaf")
            elif native_class(value):
                pass
            elif kind is BuiltinFunctionType:
                if not any(value is function for function in (*native_builtin_functions, *native_c_functions)):
                    raise ValueError("Configured native function leaf")
            elif any(value is descriptor for descriptor in native_getsets):
                pass
            else:
                raise ValueError("Configured parser leaf")

        # Resolve the effective registry entirely through admitted raw MRO
        # namespaces; an inherited property is never used as an eligibility read.
        registry = _MISSING
        for cls in _type_field(_module_namespace(loader)["SafeLoader"], "__mro__"):
            declaration = _type_field(cls, "__dict__")
            namespace_keys(declaration)
            if "yaml_constructors" in declaration:
                registry = declaration["yaml_constructors"]
                break
        expected = {"null": "construct_yaml_null", "bool": "construct_yaml_bool",
            "int": "construct_yaml_int", "float": "construct_yaml_float",
            "binary": "construct_yaml_binary", "timestamp": "construct_yaml_timestamp",
            "omap": "construct_yaml_omap", "pairs": "construct_yaml_pairs",
            "set": "construct_yaml_set", "str": "construct_yaml_str",
            "seq": "construct_yaml_seq", "map": "construct_yaml_map"}
        expected_keys = {None, *("tag:yaml.org,2002:" + name for name in expected)}
        if (type(registry) is not dict
                or any(type(key) is not str and key is not None for key in registry)
                or set(registry) != expected_keys):
            raise ValueError("Configured constructor registry")
        safe_namespace = _type_field(_module_namespace(constructor)["SafeConstructor"], "__dict__")
        for name, method in expected.items():
            function = safe_namespace.get(method)
            _function_code(function)
            if registry["tag:yaml.org,2002:" + name] is not function:
                raise ValueError("Configured YAML constructor")
        if registry[None] is not safe_namespace.get("construct_undefined"):
            raise ValueError("Configured undefined constructor")

        for cls in classes:
            mro = _type_field(cls, "__mro__")
            self.classes.append((cls, type(cls), mro))
            namespace = _type_field(cls, "__dict__")
            entries = tuple(namespace.items())
            self.namespaces.append((namespace, entries, True))
            for _name, value in entries:
                function = (object.__getattribute__(value, "__func__")
                            if type(value) is staticmethod or type(value) is classmethod else value)
                if (cls is hashable or cls is ABCMeta) and type(function) is FunctionType and not any(
                        function is allowed for allowed in external_functions):
                    # ABC registration/debug functions are declaration-bound,
                    # not executed by this parser's native scalar-key checks.
                    code = _function_code(function)
                    owner = _collections_abc if cls is hashable else abc
                    filename = _module_namespace(owner).get("__file__")
                    frozen_name = "<frozen _collections_abc>" if cls is hashable else "<frozen abc>"
                    if (function.__globals__ is not _module_namespace(owner) or type(filename) is not str
                            or code.co_filename != filename and code.co_filename != frozen_name):
                        raise ValueError("Configured ABC declaration")
                    self.functions.append((function, code, function.__defaults__,
                                           function.__kwdefaults__, function.__closure__))
                    capture(function.__defaults__); capture(function.__kwdefaults__)
                    for cell in function.__closure__ or ():
                        self.bindings.append((cell, None, cell.cell_contents))
                        capture(cell.cell_contents)
                    continue
                capture(value)
        for module in yaml_modules:
            for name, value in _module_namespace(module).items():
                if not name.startswith("__"):
                    capture(value)
        for name in ("safe_load", "load", "SafeLoader"):
            self.bindings.append((_module_namespace(yaml), name, _module_namespace(yaml)[name]))
        capture(_module_namespace(yaml)["safe_load"]); capture(_module_namespace(yaml)["load"])
        for module, names in ((dates, ("date", "datetime", "timedelta", "timezone")),
                (collections, ("abc",)), (collections_abc, ("Hashable",)),
                (re, ("Pattern",)), (abc, ("ABCMeta",)),
                (base64, ("decodebytes", "_input_type_check")),
                (binascii, ("Error", "a2b_base64"))):
            namespace_keys(_module_namespace(module))
            for name in names:
                self.bindings.append((_module_namespace(module), name, _module_namespace(module).get(name, _MISSING)))
        for function in external_functions:
            capture(function)

    def matches(self):
        try:
            if any(type(module) is not ModuleType for module in self.modules):
                return False
            if any(any(type(name) is not str for name in namespace)
                   for namespace in self.key_namespaces):
                return False
            for namespace, entries, complete in self.namespaces:
                if any(type(k) is not str for k in namespace):
                    return False
                if complete:
                    if len(namespace) != len(entries):
                        return False
                elif tuple(k for k in namespace if not k.startswith("__")) != tuple(k for k, _ in entries):
                    return False
                if any(namespace.get(name, _MISSING) is not value for name, value in entries):
                    return False
            for cls, metaclass, mro in self.classes:
                if type(cls) is not metaclass or _type_field(cls, "__mro__") is not mro:
                    return False
            for function, code, defaults, keywords, closure in self.functions:
                if (function.__code__ is not code or function.__defaults__ is not defaults
                        or function.__kwdefaults__ is not keywords or function.__closure__ is not closure):
                    return False
            for container, saved, mapping in self.containers:
                if len(container) != len(saved):
                    return False
                if mapping:
                    if any(not any(type(k) is t for t in (str, type(None), int)) for k in container):
                        return False
                    if any(container.get(k, _MISSING) is not v for k, v in saved):
                        return False
                elif any(a is not b for a, b in zip(container, saved)):
                    return False
            for namespace, name, expected in self.bindings:
                if name is None:
                    if namespace.cell_contents is not expected:
                        return False
                elif type(namespace) is dict:
                    if namespace.get(name, _MISSING) is not expected:
                        return False
                elif type(namespace) is _PATTERN:
                    # Native patterns are immutable; no user getter is bound.
                    actual = namespace.pattern if name == "pattern" else namespace.flags
                    if (name == "pattern" and type(actual) is not str
                            or name == "flags" and type(actual) is not int
                            or actual != expected):
                        return False
                else:
                    return False
            return True
        except (AttributeError, TypeError, ValueError, RuntimeError):
            return False


try:
    _RECIPE = _StockYamlRecipe()
except (AttributeError, TypeError, ValueError, RuntimeError):
    _RECIPE = None

_CACHE = OrderedDict()
_LOCK = Lock()
_CHARGE = 0


def _freeze(value):
    seen = set()
    count = 0
    charge = 0

    def visit(item, depth):
        nonlocal count, charge
        count += 1
        if count > _MAX_NODES or depth > _MAX_DEPTH:
            raise ValueError("Unbounded parsed content")
        kind = type(item)
        if not any(kind is t for t in (dict, list, type(None), bool, int, str, float, date)):
            raise ValueError("Unsupported parsed content")
        charge += _NATIVE_GETSIZE(item) + 128
        if charge > _MAX_BYTES:
            raise ValueError("Oversize parsed content")
        if kind is dict or kind is list:
            identity = id(item)
            if identity in seen:
                raise ValueError("Aliased parsed content keeps ordinary parsing")
            seen.add(identity)
            if kind is list:
                return ("list", tuple(visit(v, depth + 1) for v in item))
            return ("dict", tuple((visit(k, depth + 1), visit(v, depth + 1)) for k, v in item.items()))
        if any(kind is t for t in (type(None), bool, int, str)):
            return ("scalar", item)
        if kind is float and _NATIVE_ISFINITE(item):
            return ("float", item.hex())
        if kind is date:
            return ("date", item.year, item.month, item.day)
        # Timestamps, binary, sets and configured tags remain ordinary until
        # their full external constructor/representation contract is admitted.
        raise ValueError("Unsupported parsed content")

    frozen = visit(value, 0)
    return frozen, charge


def _thaw(value):
    count = 0

    def visit(item, depth):
        nonlocal count
        count += 1
        if (count > _MAX_NODES or depth > _MAX_DEPTH or type(item) is not tuple
                or not item or type(item[0]) is not str):
            raise ValueError("Invalid parsed content")
        tag = item[0]
        if tag == "scalar" and len(item) == 2 and any(
                type(item[1]) is t for t in (type(None), bool, int, str)):
            return item[1]
        if tag == "float" and len(item) == 2 and type(item[1]) is str:
            result = float.fromhex(item[1])
            if _NATIVE_ISFINITE(result):
                return result
        if tag == "date" and len(item) == 4 and all(type(v) is int for v in item[1:]):
            return date(*item[1:])
        if tag in ("list", "dict") and len(item) == 2 and type(item[1]) is tuple:
            if tag == "list":
                return [visit(v, depth + 1) for v in item[1]]
            result = {}
            for pair in item[1]:
                if type(pair) is not tuple or len(pair) != 2:
                    raise ValueError("Invalid parsed mapping")
                result[visit(pair[0], depth + 1)] = visit(pair[1], depth + 1)
            return result
        raise ValueError("Unknown parsed content")

    return visit(value, 0)


def clear_pure_content():
    """Drop content only; never perform an I/O, proof, transaction or callback."""
    global _CHARGE
    with _LOCK:
        _CACHE.clear()
        _CHARGE = 0


def load_yaml_text(text, *, parse=_MISSING):
    """The ordinary parser once, or detached stock pure content.

    Parser exceptions and representation declines are never cached or replayed.
    Every source/authorization consumer still performs its live checks.
    """
    global _CHARGE
    ordinary = yaml.safe_load if parse is _MISSING else parse
    if (ordinary is not _STOCK_PARSE or type(text) is not str
            or not _MIN_INPUT <= len(text) <= _MAX_INPUT
            or _RECIPE is None):
        return ordinary(text)
    try:
        if len(text.encode("utf-8")) > _MAX_INPUT:
            return ordinary(text)
    except UnicodeError:
        return ordinary(text)
    if not _RECIPE.matches():
        clear_pure_content()
        return ordinary(text)
    with _LOCK:
        entry = _CACHE.get(text)
        if entry is not None:
            _CACHE.move_to_end(text)
    if entry is not None:
        try:
            if (type(entry) is not tuple or len(entry) != 2
                    or type(entry[1]) is not int or not 0 < entry[1] <= _MAX_BYTES):
                raise ValueError("Invalid parsed envelope")
            value = _thaw(entry[0])
        except (IndexError, KeyError, TypeError, ValueError, RecursionError):
            clear_pure_content()
        else:
            if _RECIPE.matches():
                return value
            clear_pure_content()
        # No parser producer entered on a content hit.
        return ordinary(text)
    value = ordinary(text)
    if not _RECIPE.matches():
        clear_pure_content()
        return value
    try:
        frozen, charge = _freeze(value)
        charge += 4 * len(text) + 512
        if charge > _MAX_BYTES or not _RECIPE.matches():
            return value
    except (TypeError, ValueError, RecursionError):
        return value
    with _LOCK:
        # Concurrent identical pure parsing is harmless; do not double charge.
        if text not in _CACHE:
            while _CACHE and (len(_CACHE) >= _MAX_ENTRIES or _CHARGE + charge > _MAX_BYTES):
                _old, old_entry = _CACHE.popitem(last=False)
                if (type(old_entry) is not tuple or len(old_entry) != 2
                        or type(old_entry[1]) is not int or not 0 < old_entry[1] <= _MAX_BYTES):
                    _CACHE.clear()
                    _CHARGE = 0
                    break
                old_charge = old_entry[1]
                _CHARGE -= old_charge
            _CACHE[text] = (frozen, charge)
            _CHARGE += charge
    # The completed ordinary parse is returned once; its graph is not retained.
    return value
