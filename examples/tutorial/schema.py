# -*- coding: utf-8 -*-
import datetime

from pydantic import Field

from fast_grpc import BaseSchema
from fast_grpc.types import Int32, IntEnum


class HelloRequest(BaseSchema):
    name: str


class Data(BaseSchema):
    name: str
    value: int
    age: Int32


class Language(IntEnum):
    LANGUAGE_UNKNOWN = 0, "未知", "UNKNOWN"
    LANGUAGE_ZH = 1, "中文", "Chinese"
    LANGUAGE_EN = 2, "英文", "English"


class HelloReply(BaseSchema):
    message: str
    data: Data
    language: Language


class OkReply(BaseSchema):
    message: str = "ok"
    create_at: datetime.datetime = Field(default_factory=datetime.datetime.now)
