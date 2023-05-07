# -*- coding: utf-8 -*-
import datetime

from pydantic import BaseModel


class BaseSchema(BaseModel):
    class Config:
        orm_mode = True
        json_encoders = {
            datetime.datetime: lambda v: int(v.timestamp()),
        }
