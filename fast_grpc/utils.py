# -*- coding: utf-8 -*-
import asyncio
import contextvars
import functools
import importlib.util
import os
import re
import subprocess
import sys
import inspect
from importlib import import_module
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    AsyncIterator,
    get_origin,
    get_args,
    AsyncIterable,
    ForwardRef,
    Optional,
    Sequence,
)

from google.protobuf.json_format import MessageToDict, Parse, ParseDict
from google.protobuf.text_format import MessageToString
from logzero import logger
from pydantic._internal._typing_extra import eval_type_lenient


def import_string(dotted_path):
    try:
        module_path, class_name = dotted_path.rsplit(".", 1)
    except ValueError as err:
        raise ImportError("%s doesn't look like a module path" % dotted_path) from err

    module = import_module(module_path)

    try:
        return getattr(module, class_name)
    except AttributeError as err:
        raise ImportError(
            'Module "%s" does not define a "%s" attribute/class'
            % (module_path, class_name)
        ) from err


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
    # 在小写字母和大写字母的边界添加下划线（避免全大写被逐字母拆分）
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", name)
    # 将连续的大写字母拆分成单词，但保留整体（如HTTP保持不被逐字母拆分）
    name = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", name)
    # 转为小写
    return name.lower()


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


def load_model_from_file_location(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    proto_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proto_module)
    return proto_module


def import_proto_file(proto_path: Path):
    # 获取 proto 文件的基础名称，去掉扩展名
    # base_name = os.path.splitext(os.path.basename(proto_file_path))[0]
    base_name = proto_path.stem

    # # 拼接生成的 Python 文件路径，假设生成的文件名为 base_name_pb2.py
    # pb2_file_path = os.path.join(
    #     os.path.dirname(proto_file_path), f"{base_name}_pb2.py"
    # )
    # pb2_grpc_file_path = os.path.join(
    #     os.path.dirname(proto_file_path), f"{base_name}_pb2_grpc.py"
    # )
    pb2_file_path = proto_path.parent / f"{base_name}_pb2.py"
    pb2_grpc_file_path = proto_path.parent / f"{base_name}_pb2_grpc.py"
    # 检查生成的 Python 文件是否存在
    if not pb2_file_path.exists():
        raise FileNotFoundError(f"生成的 pb2 文件 {pb2_file_path} 不存在。")
    if not pb2_grpc_file_path.exists():
        raise FileNotFoundError(f"生成的 pb2 文件 {pb2_grpc_file_path} 不存在。")

    # 动态加载模块
    _pb2 = load_model_from_file_location(f"{base_name}_pb2.py", pb2_file_path)
    _pb2_grpc = load_model_from_file_location(
        f"{base_name}_pb2_grpc.py", pb2_grpc_file_path
    )

    return _pb2, _pb2_grpc


def message_to_dict(message):
    return MessageToDict(
        message, including_default_value_fields=True, preserving_proto_field_name=True
    )


def json_to_message(data, message_cls):
    return Parse(data, message_cls(), ignore_unknown_fields=True)


def dict_to_message(data, message_cls):
    return ParseDict(data, message_cls(), ignore_unknown_fields=True)


def message_to_str(message_or_iterator) -> str:
    if isinstance(message_or_iterator, AsyncIterator):
        return "<StreamingMessage(...)>"
    return MessageToString(message_or_iterator, as_one_line=True, force_colon=True)


def message_to_pydantic(message, pydantic_model):
    """Convert protobuf message to pydantic model"""
    return pydantic_model.model_validate(message, from_attributes=True)


def pydantic_to_message(schema, message_cls):
    """Convert pydantic model to protobuf message"""
    return Parse(schema.model_dump_json(), message_cls(), ignore_unknown_fields=True)


def get_param_annotation_model(annotation, is_streaming=False):
    if annotation is inspect.Signature.empty:
        return None
    if not is_streaming:
        return annotation
    origin_type = get_origin(annotation)
    args = get_args(annotation)
    if not issubclass(origin_type, AsyncIterable):
        return None
    return args[0] if args else None


def get_typed_annotation(annotation: Any, _globals: Dict[str, Any]) -> Any:
    if isinstance(annotation, str):
        annotation = ForwardRef(annotation)
        annotation = eval_type_lenient(annotation, _globals, _globals)
    return annotation


def get_typed_signature(call: Callable[..., Any]) -> inspect.Signature:
    signature = inspect.signature(call)
    _globals = getattr(call, "__globals__", {})
    typed_params = [
        inspect.Parameter(
            name=param.name,
            kind=param.kind,
            default=param.default,
            annotation=get_typed_annotation(param.annotation, _globals),
        )
        for param in signature.parameters.values()
    ]
    typed_signature = inspect.Signature(
        typed_params,
        return_annotation=get_typed_annotation(signature.return_annotation, _globals),
    )
    return typed_signature


def protoc_compile(
    proto: Path,
    python_out=".",
    grpc_python_out=".",
    proto_paths: Optional[Sequence[str]] = None,
):
    """
    python -m grpc_tools.protoc --python_out=. --grpc_python_out=. --mypy_out=. -I. demo.proto
    """
    if not proto.exists():
        raise FileNotFoundError(f"Proto file or directory '{proto}' not found")
    if proto.is_file():
        proto_dir = proto.parent
    else:
        proto_dir = proto
    proto_files = [
        str(f) for f in proto_dir.iterdir() if f.is_file() and f.name.endswith(".proto")
    ]
    protoc_args = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"--python_out={python_out}",
        f"--grpc_python_out={grpc_python_out}",
        "-I.",
    ]
    if proto_paths is not None:
        protoc_args.extend([f"-I{p}" for p in proto_paths])
    for file in proto_files:
        protoc_args.append(file)
    status_code = subprocess.call(protoc_args)
    if status_code != 0:
        logger.error(f"Command `{' '.join(protoc_args)}` [Err] {status_code=}")
        raise RuntimeError("Protobuf compilation failed")
    logger.info(f"Compiled {proto} success")
