# -*- coding: utf-8 -*-
from typing import (
    Awaitable,
    Callable,
    TypeVar,
    Sequence,
    Tuple,
    Union,
    AsyncIterable,
    Annotated,
)

from pydantic import BaseModel, Field
from typing_extensions import TypeAlias

from fast_grpc.context import ServiceContext

Request = TypeVar("Request")
Response = TypeVar("Response")

Method = Callable[
    [Request, ServiceContext], Union[AsyncIterable[Response], Awaitable[Response]]
]
MetadataType = Sequence[Tuple[str, Union[str, bytes]]]


class Empty(BaseModel):
    pass


class ProtoTag:
    def __init__(self, name: str, package: str = ""):
        self.name = name
        self.package = package


Uint32: TypeAlias = Annotated[int, Field(ge=0, lt=2**32), ProtoTag(name="uint32")]
Uint64: TypeAlias = Annotated[int, Field(ge=0, lt=2**64), ProtoTag(name="uint64")]
Int32: TypeAlias = Annotated[int, Field(ge=-(2**31), lt=2**31), ProtoTag(name="int32")]
Int64: TypeAlias = Annotated[int, Field(ge=-(2**63), lt=2**63), ProtoTag(name="int64")]
Double: TypeAlias = Annotated[float, ProtoTag(name="double")]
