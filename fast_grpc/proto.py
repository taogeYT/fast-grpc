# -*- coding: utf-8 -*-
import datetime
from enum import IntEnum
from typing import Type, Sequence, Any

from pydantic import BaseModel
from typing_extensions import get_args, get_origin
from jinja2 import Template

from fast_grpc.service import Service, MethodMode
from fast_grpc.types import Empty
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
    datetime.datetime: "string",
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

# 定义 Jinja2 模板
PROTO_TEMPLATE = """
syntax = "proto3";

package {{ proto_define.package }};

{% for service in proto_define.services %}
service {{ service.name }} {
    {% for method in service.methods -%}
    rpc {{ method.name }}({{ method.request }}) returns ({{ method.response }});
    {%- if not loop.last %}
    {% endif %}
    {%- endfor %}
}
{% endfor %}
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
""".strip()


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


class ProtoService(BaseModel):
    name: str
    methods: list[ProtoMethod]


class ProtoDefine(BaseModel):
    package: str
    services: list[ProtoService]
    messages: dict[Any, ProtoStruct]
    enums: dict[Any, ProtoStruct]


def generate_type_name(type_: type) -> str:
    """Generate a name for generic type by combining base name and type arguments.
    Example: Response[User] -> UserResponse
            Page[User] -> UserPage
            NestedResponse[User, DataList] -> UserDataListNestedResponse
    """
    if not isinstance(type_, type):
        raise ValueError(f"'{type_}' must be a type")
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
        if not issubclass(type_, tuple(_base_types)):
            raise ValueError(f"Unsupported type: {type_}")
        return type_.__name__.capitalize()
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
        for i, (name, field) in enumerate(schema.model_fields.items(), 1):
            type_name = self._get_type_name(field.annotation)
            message.fields.append(ProtoField(name=name, type=type_name, index=i))
        self._proto_define.messages[schema] = message
        return message

    def convert_enum(self, schema: Type[IntEnum]):
        if schema in self._proto_define.enums:
            return self._proto_define.enums[schema]
        enum_struct = ProtoStruct(
            name=schema.__name__,
            fields=[
                ProtoField(name=member.name, index=member.value) for member in schema
            ],
        )
        self._proto_define.enums[schema] = enum_struct
        return enum_struct

    def _get_type_name(self, type_: type) -> str:
        origin = get_origin(type_)
        args = get_args(type_)
        if origin is None:
            if issubclass(type_, BaseModel):
                message = self.convert_message(type_)
                return message.name
            if issubclass(type_, IntEnum):
                struct = self.convert_enum(type_)
                return struct.name
            if not issubclass(type_, tuple(_base_types)):
                raise ValueError(f"Unsupported type: {type_}")
            return _base_types[type_]
        else:
            if issubclass(origin, Sequence):
                return f"repeated {self._get_type_name(args[0])}"
            if issubclass(origin, dict):
                return f"map <{self._get_type_name(args[0])}, {self._get_type_name(args[1])}>"
            raise ValueError(f"Unsupported type: {type_}")


def render_proto_file(proto_define: ProtoDefine, proto_template=PROTO_TEMPLATE) -> str:
    template = Template(proto_template)
    return template.render(proto_define=proto_define)


def save_proto_file(proto_define: ProtoDefine, proto_template=PROTO_TEMPLATE):
    content = render_proto_file(
        proto_define=proto_define, proto_template=proto_template
    )
    with open(proto_define.proto, "w") as f:
        f.write(content)
