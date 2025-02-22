# -*- coding: utf-8 -*-
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field


class Empty(BaseModel):
    pass


class ProtoTag:
    __slots__ = ("name", "package")

    def __init__(self, name: str, package: str = ""):
        self.name = name
        self.package = package


# Python -> Protobuf
PYTHON_TO_PROTOBUF_TYPES = {
    bytes: ProtoTag("bytes"),
    int: ProtoTag("int32"),
    float: ProtoTag("float"),
    bool: ProtoTag("bool"),
    str: ProtoTag("string"),
    datetime: ProtoTag("string"),
}


Uint32 = Annotated[int, Field(ge=0, lt=2**32), ProtoTag(name="uint32")]
Uint64 = Annotated[int, Field(ge=0, lt=2**64), ProtoTag(name="uint64")]
Int32 = Annotated[int, Field(ge=-(2**31), lt=2**31), ProtoTag(name="int32")]
Int64 = Annotated[int, Field(ge=-(2**63), lt=2**63), ProtoTag(name="int64")]
Double = Annotated[float, ProtoTag(name="double")]
