from enum import IntEnum
from typing import List, Optional, Union

import pytest
from pydantic import BaseModel

from fast_grpc.proto import (
    ClientBuilder,
    ProtoBuilder,
    ProtoDefine,
    ProtoField,
    ProtoService,
    ProtoStruct,
    generate_type_name,
)
from fast_grpc.types import ProtoTag


class SimpleModel(BaseModel):
    name: str
    age: int


class StatusEnum(IntEnum):
    ACTIVE = 0
    INACTIVE = 1


class TestGenerateTypeName:
    def test_basemodel(self):
        assert generate_type_name(SimpleModel) == "SimpleModel"

    def test_int_enum(self):
        assert generate_type_name(StatusEnum) == "StatusEnum"

    def test_builtin_types(self):
        assert generate_type_name(str) == "Str"
        assert generate_type_name(int) == "Int"
        assert generate_type_name(bool) == "Bool"

    def test_unsupported_type_raises(self):
        with pytest.raises(ValueError, match="must be a type"):
            generate_type_name(Union[str, int])


class TestProtoField:
    def test_proto_string(self):
        field = ProtoField(name="name", index=1, type="string")
        assert field.proto_string == "string name = 1"

    def test_proto_string_empty_type(self):
        field = ProtoField(name="id", index=1, type="")
        assert field.proto_string == "id = 1"


class TestProtoBuilderGetTypeName:
    def setup_method(self):
        self.builder = ProtoBuilder("test_package")

    def test_str_type(self):
        assert self.builder._get_type_name(str) == "string"

    def test_int_type(self):
        assert self.builder._get_type_name(int) == "int32"

    def test_float_type(self):
        assert self.builder._get_type_name(float) == "float"

    def test_bool_type(self):
        assert self.builder._get_type_name(bool) == "bool"

    def test_bytes_type(self):
        assert self.builder._get_type_name(bytes) == "bytes"

    def test_basemodel_type(self):
        result = self.builder._get_type_name(SimpleModel)
        assert result == "SimpleModel"

    def test_sequence_type(self):
        from typing import List
        result = self.builder._get_type_name(List[str])
        assert result == "repeated string"

    def test_dict_type(self):
        from typing import Dict
        result = self.builder._get_type_name(Dict[str, int])
        assert result == "map <string, int32>"

    def test_optional_type(self):
        result = self.builder._get_type_name(Optional[str])
        assert result == "string"

    def test_annotated_with_proto_tag(self):
        from typing import Annotated
        MyType = Annotated[int, ProtoTag("uint32")]
        result = self.builder._get_type_name(MyType)
        assert result == "uint32"

    def test_custom_type_mapping(self):
        from fast_grpc.types import PYTHON_TO_PROTOBUF_TYPES
        original_str_tag = PYTHON_TO_PROTOBUF_TYPES.get(str)
        try:
            builder = ProtoBuilder("test", type_mapping={str: ProtoTag("custom_string")})
            assert builder._get_type_name(str) == "custom_string"
        finally:
            # Restore original mapping (ProtoBuilder.__init__ mutates the global dict)
            if original_str_tag:
                PYTHON_TO_PROTOBUF_TYPES[str] = original_str_tag

    def test_string_literal_passthrough(self):
        assert self.builder._get_type_name("int64") == "int64"


class TestProtoBuilderConvertMessage:
    def setup_method(self):
        from fast_grpc.types import PYTHON_TO_PROTOBUF_TYPES
        self.builder = ProtoBuilder("test_package", type_mapping=dict(PYTHON_TO_PROTOBUF_TYPES))

    def test_creates_proto_struct_with_fields(self):
        result = self.builder.convert_message(SimpleModel)
        assert isinstance(result, ProtoStruct)
        assert result.name == "SimpleModel"
        assert len(result.fields) == 2
        assert result.fields[0].name == "name"
        assert result.fields[0].type == "string"
        assert result.fields[0].index == 1
        assert result.fields[1].name == "age"
        assert result.fields[1].type == "int32"
        assert result.fields[1].index == 2

    def test_caches_message(self):
        first = self.builder.convert_message(SimpleModel)
        second = self.builder.convert_message(SimpleModel)
        assert first is second


class TestProtoDefineRender:
    def test_render_proto_file(self):
        msg = ProtoStruct(
            name="HelloRequest",
            fields=[ProtoField(name="name", index=1, type="string")],
        )
        svc = ProtoService(name="Greeter", methods=[])
        define = ProtoDefine(
            package="test",
            services=[svc],
            messages={SimpleModel: msg},
            enums={},
        )
        result = define.render_proto_file()
        assert "package test;" in result
        assert "message HelloRequest" in result
        assert "string name = 1" in result

    def test_render_python_client(self):
        msg = ProtoStruct(name="Req", fields=[])
        svc = ProtoService(name="TestSvc", methods=[])
        define = ProtoDefine(
            package="test",
            services=[svc],
            messages={SimpleModel: msg},
            enums={},
        )
        result = define.render_python_file(is_async=False)
        assert "class TestSvcClient" in result
        assert "class Req" in result
