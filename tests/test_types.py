from datetime import datetime
from uuid import UUID
from typing import get_args

import pytest
from pydantic import BaseModel

from fast_grpc.types import (
    Double,
    Empty,
    Int32,
    Int64,
    ProtoTag,
    PYTHON_TO_PROTOBUF_TYPES,
    Uint32,
    Uint64,
)


class TestEmpty:
    def test_instantiation(self):
        assert Empty() is not None

    def test_is_pydantic_model(self):
        assert issubclass(Empty, BaseModel)

    def test_no_fields(self):
        assert len(Empty.model_fields) == 0


class TestProtoTag:
    def test_name_only(self):
        tag = ProtoTag("int32")
        assert tag.name == "int32"
        assert tag.package == ""

    def test_name_and_package(self):
        tag = ProtoTag("Timestamp", "google.protobuf")
        assert tag.name == "Timestamp"
        assert tag.package == "google.protobuf"

    def test_slots(self):
        tag = ProtoTag("string")
        with pytest.raises(AttributeError):
            tag.some_attr = "should fail"


class TestPythonToProtobufTypes:
    def test_basic_types_present(self):
        assert bytes in PYTHON_TO_PROTOBUF_TYPES
        assert int in PYTHON_TO_PROTOBUF_TYPES
        assert float in PYTHON_TO_PROTOBUF_TYPES
        assert bool in PYTHON_TO_PROTOBUF_TYPES
        assert str in PYTHON_TO_PROTOBUF_TYPES
        assert datetime in PYTHON_TO_PROTOBUF_TYPES
        assert UUID in PYTHON_TO_PROTOBUF_TYPES

    def test_tag_names(self):
        assert PYTHON_TO_PROTOBUF_TYPES[bytes].name == "bytes"
        assert PYTHON_TO_PROTOBUF_TYPES[int].name == "int32"
        assert PYTHON_TO_PROTOBUF_TYPES[float].name == "float"
        assert PYTHON_TO_PROTOBUF_TYPES[bool].name == "bool"
        assert PYTHON_TO_PROTOBUF_TYPES[str].name == "string"
        assert PYTHON_TO_PROTOBUF_TYPES[datetime].name == "string"
        assert PYTHON_TO_PROTOBUF_TYPES[UUID].name == "string"


def test_uint32():
    args = get_args(Uint32)
    assert args[0] is int  # base type
    # Has ProtoTag metadata
    tags = [a for a in args[1:] if isinstance(a, ProtoTag)]
    assert len(tags) == 1
    assert tags[0].name == "uint32"


def test_uint64():
    args = get_args(Uint64)
    tags = [a for a in args[1:] if isinstance(a, ProtoTag)]
    assert len(tags) == 1
    assert tags[0].name == "uint64"


def test_int32():
    args = get_args(Int32)
    tags = [a for a in args[1:] if isinstance(a, ProtoTag)]
    assert len(tags) == 1
    assert tags[0].name == "int32"


def test_int64():
    args = get_args(Int64)
    tags = [a for a in args[1:] if isinstance(a, ProtoTag)]
    assert len(tags) == 1
    assert tags[0].name == "int64"


def test_double():
    args = get_args(Double)
    assert args[0] is float  # base type
    tags = [a for a in args[1:] if isinstance(a, ProtoTag)]
    assert len(tags) == 1
    assert tags[0].name == "double"
