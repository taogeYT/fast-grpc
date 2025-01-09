# -*- coding: utf-8 -*-
from typing import (
    Awaitable,
    Callable,
    Generic,
    Optional,
    TypeVar,
    Sequence,
    Tuple,
    Union,
    AsyncIterable,
)

from pydantic import conint
from pydantic import BaseModel

from fast_grpc.context import ServiceContext

Request = TypeVar("Request")
Response = TypeVar("Response")

Method = Callable[
    [Request, ServiceContext], Union[AsyncIterable[Response], Awaitable[Response]]
]
MetadataType = Sequence[Tuple[str, Union[str, bytes]]]

Uint32 = conint(ge=0, lt=2**32)
Uint64 = conint(ge=0, lt=2**64)
Int32 = conint(ge=-(2**31), lt=2**31)
Int64 = conint(ge=-(2**63), lt=2**63)
Double = float

T = TypeVar("T", bytes, int, str, bool, float)


class WrapperValue(BaseModel, Generic[T]):
    value: T


DoubleValue = Optional[WrapperValue[Double]]
FloatValue = Optional[WrapperValue[float]]
Int64Value = Optional[WrapperValue[Int64]]
UInt64Value = Optional[WrapperValue[Uint64]]
Int32Value = Optional[WrapperValue[Int32]]
UInt32Value = Optional[WrapperValue[Uint32]]
BoolValue = Optional[WrapperValue[bool]]
StringValue = Optional[WrapperValue[str]]
BytesValue = Optional[WrapperValue[bytes]]


class Empty(BaseModel):
    pass
