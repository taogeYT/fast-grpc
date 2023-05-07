# -*- coding: utf-8 -*-
import asyncio
import contextvars
import functools
import inspect
import os
import re
import sys
from importlib import import_module
from typing import Callable


def import_string(dotted_path):
    try:
        module_path, class_name = dotted_path.rsplit(".", 1)
    except ValueError as err:
        raise ImportError("%s doesn't look like a module path" % dotted_path) from err

    module = import_module(module_path)

    try:
        return getattr(module, class_name)
    except AttributeError as err:
        raise ImportError('Module "%s" does not define a "%s" attribute/class' % (module_path, class_name)) from err


def get_project_root_path(mod_name: str) -> str:
    mod = sys.modules.get(mod_name)

    if mod is not None and hasattr(mod, "__file__") and mod.__file__ is not None:
        return os.path.dirname(os.path.abspath(mod.__file__))
    return os.getcwd()


def is_camel_case(name):
    return re.match(r"^(?:[A-Z][a-z]+)*$", name) is not None


def is_snake_case(name):
    if not name:
        return False
    if name[0] == "_" or name[-1] == "_":
        return False
    if any(c.isupper() for c in name):
        return False
    if "__" in name:
        return False
    if not all(c.isalnum() or c == "_" for c in name):
        return False
    if "_" not in name:
        return False
    return True


def camel_to_snake(name):
    """
    Replace uppercase letters with _+lowercase letters, for example "FastGRPC" -> "fast_grpc"
    """
    snake_case_str = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    if snake_case_str.startswith("_"):
        snake_case_str = snake_case_str[1:]
    return snake_case_str


def snake_to_camel(name):
    parts = name.split("_")
    camel_name = "".join(word.capitalize() for word in parts)
    return camel_name


def await_sync_function(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        context = contextvars.copy_context()
        args = (functools.partial(func, *args, **kwargs),)
        return await loop.run_in_executor(None, context.run, args)

    return wrapper
