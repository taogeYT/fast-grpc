# -*- coding: utf-8 -*-
from enum import IntEnum as _IntEnum
from typing import TYPE_CHECKING, Awaitable, Callable, Generic, Optional, TypeVar, Union

from google.protobuf.message import Message
from grpc.aio import ServicerContext
from logzero import logger
from pydantic import ConstrainedInt
from pydantic.generics import GenericModel

from fast_grpc.base import BaseSchema

Handler = Callable[[BaseSchema, ServicerContext], Awaitable[BaseSchema]]
App = Callable[[Message, ServicerContext, Handler], Awaitable[Message]]

if TYPE_CHECKING:
    Uint32 = int
    Uint64 = int
    Int32 = int
    Int64 = int
    Double = float
else:

    class Uint32(ConstrainedInt):
        ge = 0
        lt = 2**32

    class Uint64(ConstrainedInt):
        ge = 0
        lt = 2**64

    class Int32(ConstrainedInt):
        ge = -(2**31)
        lt = 2**31

    class Int64(ConstrainedInt):
        ge = -(2**63)
        lt = 2**31

    class Double(float):
        pass


T = TypeVar("T", bytes, int, str, bool, float, Uint32, Uint64, Int32, Int64, Double)


class WrapperValue(GenericModel, Generic[T]):
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


class Empty(BaseSchema):
    pass


class IntEnum(_IntEnum):
    """
    IntEnum support custom attribute
    Example:
        class Language(IntEnum):
            LANGUAGE_UNKNOWN = 0, "未知", "UNKNOWN"
            LANGUAGE_ZH = 1, "中文", "Chinese"
            LANGUAGE_EN = 2, "英文", "English"

            @property
            def chinese_description(self) -> str:
                return self._get_attribute(0, "")

            @property
            def english_description(self) -> str:
                return self._get_attribute(1, "")

        print(
            Language.LANGUAGE_ZH.value,
            Language.LANGUAGE_ZH.chinese_description,
            Language.LANGUAGE_ZH.english_description,
        )
    """

    def __new__(cls, value: int, *args):
        obj = int.__new__(cls, value)  # noqa
        obj._value_ = value
        setattr(obj, "_args", args)
        return obj

    def _get_attribute(self, index, default):
        return self._args[index] if len(self._args) > index else default

    @property
    def description(self) -> str:
        return self._get_attribute(0, "")

    @property
    def swagger_description(self):
        if self.description:
            return f"{self.name.upper()}: {self.value} // {self.description}"
        else:
            return f"{self.name.upper()}: {self.value}"

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema["description"] = "<br>".join([e.swagger_description for e in cls])

    @classmethod
    def _missing_(cls, value):
        logger.info(f"{cls.__qualname__} missing {value=}")
        unknown = cls._value2member_map_.get(0)
        if not isinstance(value, int) and unknown is None:
            raise ValueError("%r is not a valid %s" % (value, cls.__qualname__))
        return unknown
