# -*- coding: utf-8 -*-
import datetime
from collections import deque
from enum import IntEnum
from typing import List, Set, Type, Union

from grpc_tools import protoc
from pydantic import BaseModel
from typing_extensions import get_args, get_origin

from fast_grpc.types import (
    BoolValue,
    BytesValue,
    Double,
    DoubleValue,
    FloatValue,
    Int32,
    Int32Value,
    Int64,
    Int64Value,
    StringValue,
    Uint32,
    UInt32Value,
    Uint64,
    UInt64Value,
)

_base_types = {
    bytes: "bytes",
    # int
    int: "int32",
    float: "float",
    # Boolean
    bool: "bool",
    # Date and time
    datetime.datetime: "int32",
    str: "string",
    Uint32: "uint32",
    Uint64: "uint64",
    Int32: "int32",
    Int64: "int64",
    Double: "double",
}

_wrapper_types = {
    BoolValue: "google.protobuf.BoolValue",
    BytesValue: "google.protobuf.BytesValue",
    DoubleValue: "google.protobuf.DoubleValue",
    FloatValue: "google.protobuf.FloatValue",
    Int32Value: "google.protobuf.Int32Value",
    Int64Value: "google.protobuf.Int64Value",
    StringValue: "google.protobuf.StringValue",
    UInt32Value: "google.protobuf.UInt32Value",
    UInt64Value: "google.protobuf.UInt64Value",
}

rpc_template = """rpc {name}({request}) returns ({response}) {{}}
"""
field_template = """{type} {name} = {index};"""
message_template = """
message {name} {{
    {content}
}}
"""

member_template = """{name} = {index};"""
enum_template = """
enum {name} {{
    {content}
}}
"""

proto_template = """syntax = "proto3";

package {package_name};
{import_package}

service {service_name} {{
    {rpc_content}
}}


// struct definition.
{message_content}
"""


class ProtoBuilder:
    def __init__(self, service):
        from fast_grpc.service import Service

        self.service: Service = service
        self.queue: deque[Union[Type[BaseModel], Type[IntEnum]]] = deque()
        self.messages: Set[Union[Type[BaseModel], Type[IntEnum]]] = set()

        self.import_packages: Set[str] = set()

    def create(self):
        rpc_methods = []
        message_contents = []
        for method in self.service.methods:
            rpc_methods.append(
                rpc_template.format(
                    name=method.name,
                    request=method.request_model.__name__,
                    response=method.response_model.__name__,
                )
            )
            message_contents.append(self.to_protobuf_struct(method.request_model))
            message_contents.append(self.to_protobuf_struct(method.response_model))
        while self.queue:
            schema = self.queue.popleft()
            if schema not in self.messages:
                message_contents.append(self.to_protobuf_struct(schema))
        return proto_template.format(
            package_name=self.service.package_name,
            import_package="".join(self.import_packages),
            service_name=self.service.service_name,
            rpc_content="".join(rpc_methods),
            message_content="".join(message_contents),
        )

    def to_protobuf_struct(self, schema: Union[Type[BaseModel], Type[IntEnum]]):
        if issubclass(schema, IntEnum):
            return self.to_protobuf_enum(schema)
        if issubclass(schema, BaseModel):
            return self.to_protobuf_message(schema)
        raise NotImplementedError(f"Unsupported type {schema}")

    def to_protobuf_message(self, schema: Type[BaseModel]):
        """
        message HelloReply {
          string message = 1;
        }
        """
        fields = []
        index = 0
        for name, field in schema.__fields__.items():
            index += 1
            if field.annotation in _wrapper_types:
                self.import_packages.add("""import "google/protobuf/wrappers.proto";""")
                type_name = _wrapper_types[field.annotation]
                fields.append(field_template.format(type=type_name, name=name, index=index))
            elif get_origin(field.annotation):
                origin = get_origin(field.annotation)
                if origin not in {list, List}:
                    raise NotImplementedError(f"Unsupported type {field.annotation}")
                type_arg = get_args(field.annotation)[0]
                if type_arg in _wrapper_types:
                    self.import_packages.add("""import "google/protobuf/wrappers.proto";""")
                    type_name = _wrapper_types[type_arg]
                    fields.append(field_template.format(type=f"repeated {type_name}", name=name, index=index))
                else:
                    if get_origin(type_arg):
                        raise NotImplementedError(f"Unsupported type {field.annotation}")
                    if type_arg in _base_types:
                        type_name = _base_types[type_arg]
                    elif issubclass(type_arg, BaseModel):
                        self.queue.append(type_arg)
                        type_name = type_arg.__name__
                    else:
                        raise NotImplementedError(f"Unsupported type {field.annotation}")
                    fields.append(field_template.format(type=f"repeated {type_name}", name=name, index=index))
            else:
                if field.annotation in _base_types:
                    type_name = _base_types[field.annotation]
                elif issubclass(field.type_, BaseModel) or issubclass(field.type_, IntEnum):
                    self.queue.append(field.type_)
                    type_name = field.type_.__name__
                else:
                    raise NotImplementedError(f"Unsupported type {field.annotation}")
                fields.append(field_template.format(type=type_name, name=name, index=index))
        self.messages.add(schema)
        return message_template.format(name=schema.__name__, content="".join(fields))

    def to_protobuf_enum(self, schema: Type[IntEnum]):
        self.messages.add(schema)
        return enum_template.format(
            name=schema.__name__,
            content="".join(member_template.format(name=member.name, index=member.value) for member in schema),
        )


def protoc_compile(name, proto_path=".", python_out=".", grpc_python_out="."):
    """
    python -m grpc_tools.protoc --python_out=. --grpc_python_out=. --mypy_out=. -I. demo.proto
    """
    proto_include = protoc.pkg_resources.resource_filename("grpc_tools", "_proto")
    protoc_args = [
        f"--proto_path={proto_path}",
        f"--python_out={python_out}",
        f"--grpc_python_out={grpc_python_out}",
        # f"--mypy_out={python_out}",
        "-I.",
        name,
    ]
    protoc_args += ["-I{}".format(proto_include)]
    status_code = protoc.main(protoc_args)

    if status_code != 0:
        raise NotImplementedError("Protobuf compilation failed")
