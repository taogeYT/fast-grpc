# -*- coding: utf-8 -*-
import datetime
import typing
from enum import IntEnum
from pathlib import Path
from typing import Type, Sequence, Any

import grpc
from pydantic import BaseModel, Field
from typing_extensions import get_args, get_origin
from jinja2 import Template
from google.protobuf.descriptor import (
    ServiceDescriptor,
    Descriptor,
    FieldDescriptor,
    EnumDescriptor,
)

from fast_grpc.service import Service, MethodMode
from fast_grpc.types import Empty, ProtoTag, PYTHON_TO_PROTOBUF_TYPES
from fast_grpc.utils import protoc_compile, camel_to_snake

_base_types = {
    bytes: "bytes",
    # int
    int: "int32",
    float: "float",
    # Boolean
    bool: "bool",
    # Date and time
    datetime.datetime: "string",
    str: "string",
}

# 定义 Jinja2 模板
PROTO_TEMPLATE = """
syntax = "proto3";

package {{ proto_define.package }};
{% for depend in proto_define.dependencies %}
{%- if depend %}
import "{{ depend }}";
{%- endif %}
{%- endfor %}
{% for enum in proto_define.enums.values() %}
enum {{ enum.name }} {
    {% for field in enum.fields -%}
    {{ field.name }} = {{ field.index }};
    {%- if not loop.last %}
    {% endif %}
    {%- endfor %}
}
{% endfor %}
{% for message in proto_define.messages.values() %}
message {{ message.name }} {
    {% for field in message.fields -%}
    {{ field.type }} {{ field.name }} = {{ field.index }};
    {%- if not loop.last %}
    {% endif %}
    {%- endfor %}
}
{% endfor %}
{% for service in proto_define.services %}
service {{ service.name }} {
    {% for method in service.methods -%}
    rpc {{ method.name }}({{ method.request }}) returns ({{ method.response }});
    {%- if not loop.last %}
    {% endif %}
    {%- endfor %}
}
{% endfor %}
"""
PYTHON_TEMPLATE = """
import grpc
from enum import IntEnum
from pydantic import BaseModel
from fast_grpc.utils import message_to_pydantic, pydantic_to_message

pb2, pb2_grpc = grpc.protos_and_services("{{ proto_define.package }}")
{% for enum in proto_define.enums.values() %}
class {{ enum.name }}(IntEnum):
    {%- for field in enum.fields %}
    {{ field.name }} = {{ field.index }}
    {%- endfor %}
{% endfor %}
{% for message in proto_define.messages.values() %}
class {{ message.name }}(BaseModel):
    {%- if message.fields %}
    {%- for field in message.fields %}
    {{ field.name }}: {{ field.type }}
    {%- endfor %}
    {% else %}
    pass
    {%- endif %}
{% endfor %}
{% for service in proto_define.services %}
class {{ service.name }}Client:
    def __init__(self, target: str="127.0.0.1:50051"):
        self.target = target

    {% for method in service.methods -%}
    def {{ method.name }}(self, request: {{ method.request }}) -> {{ method.response }}:
        with grpc.insecure_channel(self.target) as channel:
            client = pb2_grpc.{{ service.name }}Stub(channel)
            response = client.{{ method.name }}(pydantic_to_message(request, pb2.{{ method.request }}))
            return message_to_pydantic(response, {{ method.response }})

    {% endfor %}
{% endfor %}
"""


class ProtoField(BaseModel):
    name: str
    index: int
    type: str = ""

    @property
    def proto_string(self):
        return f"{self.type} {self.name} = {self.index}".strip()


class ProtoStruct(BaseModel):
    name: str
    fields: list[ProtoField]


class ProtoMethod(BaseModel):
    name: str
    request: str
    response: str
    mode: MethodMode = MethodMode.UNARY_UNARY
    client_streaming: bool = False
    server_streaming: bool = False


class ProtoService(BaseModel):
    name: str
    methods: list[ProtoMethod]


class ProtoDefine(BaseModel):
    package: str
    services: list[ProtoService]
    messages: dict[Any, ProtoStruct]
    enums: dict[Any, ProtoStruct]
    dependencies: set[str] = Field(default_factory=set)

    def render(self, proto_template) -> str:
        template = Template(proto_template)
        return template.render(proto_define=self)

    def render_proto_file(self):
        return self.render(PROTO_TEMPLATE)

    def render_python_file(self):
        return self.render(PYTHON_TEMPLATE)


def generate_type_name(type_: type) -> str:
    """Generate a name for generic type by combining base name and type arguments.
    Example: Response[User] -> UserResponse
            Page[User] -> UserPage
            NestedResponse[User, DataList] -> UserDataListNestedResponse
    """
    if not isinstance(type_, type):
        raise ValueError(f"'{type_}' must be a type")
    if type_ in (bytes, int, float, bool, str, datetime.datetime):
        return type_.__name__.capitalize()
    origin = get_origin(type_)
    args = get_args(type_)
    if origin is None:
        if issubclass(type_, BaseModel):
            # todo 字符串类型反向解析
            metadata = type_.__pydantic_generic_metadata__
            args = metadata["args"]
            origin = metadata["origin"] or type_
            type_names = [generate_type_name(t) for t in args]
            return "".join(type_names + [origin.__name__])
        if issubclass(type_, IntEnum):
            return type_.__name__
    else:
        if issubclass(origin, Sequence):
            return f"{generate_type_name(args[0])}List"
        if issubclass(origin, dict):
            return f"{generate_type_name(args[0])}{generate_type_name(args[1])}Dict"
    raise ValueError(f"Unsupported type: {type_}")


class ProtoBuilder:
    def __init__(self, package: str):
        self._proto_define = ProtoDefine(
            package=package, services=[], messages={}, enums={}
        )

    def add_service(self, service: Service):
        srv = ProtoService(name=service.name, methods=[])
        self._proto_define.services.append(srv)
        for name, method in service.methods.items():
            request = self.convert_message(method.request_model or Empty)
            response = self.convert_message(method.response_model or Empty)
            proto_method = ProtoMethod(
                name=name, request=request.name, response=response.name
            )
            if method.mode in {MethodMode.STREAM_UNARY, MethodMode.STREAM_STREAM}:
                proto_method.request = f"stream {proto_method.request}"
            if method.mode in {MethodMode.UNARY_STREAM, MethodMode.STREAM_STREAM}:
                proto_method.response = f"stream {proto_method.response}"
            srv.methods.append(proto_method)
        return self

    def get_proto(self):
        return self._proto_define

    def convert_message(self, schema: Type[BaseModel]) -> ProtoStruct:
        if schema in self._proto_define.messages:
            return self._proto_define.messages[schema]
        message = ProtoStruct(name=generate_type_name(schema), fields=[])
        for i, name in enumerate(schema.model_fields.keys(), 1):
            type_name = self._get_type_name(schema.__annotations__[name])
            message.fields.append(ProtoField(name=name, type=type_name, index=i))
        self._proto_define.messages[schema] = message
        return message

    def convert_enum(self, schema: Type[IntEnum]):
        if schema in self._proto_define.enums:
            return self._proto_define.enums[schema]
        member_prefix = camel_to_snake(schema.__name__).upper()
        enum_struct = ProtoStruct(
            name=schema.__name__,
            fields=[
                ProtoField(
                    name=member.name
                    if member.name.startswith(member_prefix)
                    else f"{member_prefix}_{member.name}",
                    index=member.value,
                )
                for member in schema
            ],
        )
        self._proto_define.enums[schema] = enum_struct
        return enum_struct

    def _get_type_name(self, type_: Any) -> str:
        origin = get_origin(type_)
        args = get_args(type_)
        if type_ in PYTHON_TO_PROTOBUF_TYPES:
            tag = PYTHON_TO_PROTOBUF_TYPES[type_]
            self._proto_define.dependencies.add(tag.package)
            return tag.name
        if origin is typing.Annotated:
            for tag in args[1:]:
                if isinstance(tag, ProtoTag):
                    self._proto_define.dependencies.add(tag.package)
                    return tag.name
            return self._get_type_name(args[0])
        if origin is typing.Union:
            _args = [i for i in args if i is not type(None)]
            return self._get_type_name(_args[0])
        if origin is None:
            if issubclass(type_, BaseModel):
                message = self.convert_message(type_)
                return message.name
            if issubclass(type_, IntEnum):
                struct = self.convert_enum(type_)
                return struct.name
        else:
            if issubclass(origin, Sequence):
                return f"repeated {self._get_type_name(args[0])}"
            if issubclass(origin, dict):
                return f"map <{self._get_type_name(args[0])}, {self._get_type_name(args[1])}>"
        raise ValueError(f"Unsupported type: {type_}")


class ClientBuilder:
    def __init__(self, package: str):
        self._proto_define = ProtoDefine(
            package=package, services=[], messages={}, enums={}
        )
        self.pb2 = grpc.protos(self._proto_define.package)
        self._proto_package = self.pb2.DESCRIPTOR.package

    def get_proto(self):
        for service in self.pb2.DESCRIPTOR.services_by_name.values():
            self.add_service(service)
        return self._proto_define

    def add_service(self, service: ServiceDescriptor):
        srv = ProtoService(name=service.name, methods=[])
        self._proto_define.services.append(srv)
        for name, method in service.methods_by_name.items():
            request = self.convert_message(method.input_type)
            response = self.convert_message(method.output_type)
            proto_method = ProtoMethod(
                name=name,
                request=request.name,
                response=response.name,
                client_streaming=method.client_streaming,
                server_streaming=method.server_streaming,
            )
            if method.client_streaming and method.server_streaming:
                proto_method.mode = MethodMode.STREAM_STREAM
            elif method.client_streaming:
                proto_method.mode = MethodMode.STREAM_UNARY
            elif method.server_streaming:
                proto_method.mode = MethodMode.UNARY_STREAM
            else:
                proto_method.mode = MethodMode.UNARY_UNARY
            srv.methods.append(proto_method)
        return self

    def _gen_class_name(self, name: str) -> str:
        return "_".join(name.removeprefix(f"{self._proto_package}.").split("."))

    def convert_message(self, message: Descriptor) -> ProtoStruct:
        if message in self._proto_define.messages:
            return self._proto_define.messages[message]
        name = self._gen_class_name(message.full_name)
        schema = ProtoStruct(name=name, fields=[])
        for i, field in enumerate(message.fields):
            type_name = self._get_type_name(field)
            schema.fields.append(ProtoField(name=field.name, type=type_name, index=i))
        self._proto_define.messages[message] = schema
        return schema

    def convert_enum(self, enum_meta: EnumDescriptor):
        if enum_meta in self._proto_define.enums:
            return self._proto_define.enums[enum_meta]
        name = self._gen_class_name(enum_meta.full_name)
        member_prefix = camel_to_snake(name).upper()
        enum_struct = ProtoStruct(
            name=name,
            fields=[
                ProtoField(
                    name=name.removeprefix(member_prefix).removeprefix("_"),
                    index=value.index,
                )
                for name, value in enum_meta.values_by_name.items()
            ],
        )
        self._proto_define.enums[enum_meta] = enum_struct
        return enum_struct

    def _get_type_name(self, field: FieldDescriptor) -> str:
        # 先检查是否是 map 类型
        if field.message_type and field.message_type.GetOptions().map_entry:
            # 处理 map 类型
            key_type = self._get_type_name(field.message_type.fields_by_name["key"])
            value_type = self._get_type_name(field.message_type.fields_by_name["value"])
            return f"dict[{key_type}, {value_type}]"

        # 获取基础类型
        def get_base_type() -> str:
            if field.type == FieldDescriptor.TYPE_MESSAGE:
                message = self.convert_message(field.message_type)
                return message.name
            elif field.type == FieldDescriptor.TYPE_ENUM:
                struct = self.convert_enum(field.enum_type)
                return struct.name

            type_map = {
                # 浮点数类型统一用 float
                FieldDescriptor.TYPE_DOUBLE: "float",
                FieldDescriptor.TYPE_FLOAT: "float",
                # 整数类型统一用 int
                FieldDescriptor.TYPE_INT64: "int",
                FieldDescriptor.TYPE_UINT64: "int",
                FieldDescriptor.TYPE_INT32: "int",
                FieldDescriptor.TYPE_FIXED64: "int",
                FieldDescriptor.TYPE_FIXED32: "int",
                FieldDescriptor.TYPE_UINT32: "int",
                FieldDescriptor.TYPE_SFIXED32: "int",
                FieldDescriptor.TYPE_SFIXED64: "int",
                FieldDescriptor.TYPE_SINT32: "int",
                FieldDescriptor.TYPE_SINT64: "int",
                # 其他基本类型保持不变
                FieldDescriptor.TYPE_BOOL: "bool",
                FieldDescriptor.TYPE_STRING: "str",
                FieldDescriptor.TYPE_BYTES: "bytes",
            }

            if field.type in type_map:
                return type_map[field.type]

            raise ValueError(f"Unsupported field type: {field.type}")

        base_type = get_base_type()

        # 处理普通的 repeated 字段
        if field.label == FieldDescriptor.LABEL_REPEATED:
            return f"list[{base_type}]"

        return base_type


def proto_to_python_client(proto_path: str):
    protoc_compile(Path(proto_path))
    builder = ClientBuilder(proto_path)
    proto_define = builder.get_proto()
    return proto_define.render_python_file()
