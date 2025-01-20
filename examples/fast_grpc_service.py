import datetime
from enum import IntEnum
from pydantic import Field, BaseModel

from fast_grpc import Service, FastGRPC
from fast_grpc.types import Empty, Int32


class HelloRequest(BaseModel):
    name: str


class Data(BaseModel):
    name: str
    value: int
    age: Int32


class Language(IntEnum):
    LANGUAGE_UNKNOWN = 0
    LANGUAGE_ZH = 1
    LANGUAGE_EN = 2


class HelloReply(BaseModel):
    message: str
    data: Data
    language: Language


class OkReply(BaseModel):
    message: str = "ok"
    create_at: datetime.datetime = Field(default_factory=datetime.datetime.now)


srv = Service("FastGRPC")


@srv.unary_unary()
async def say_hello(request: HelloRequest) -> HelloReply:
    return HelloReply(
        message=f"hello {request.name}",
        data=Data(name="grpc", value=1, age=18),
        language=Language.LANGUAGE_ZH,
    )


@srv.unary_unary()
async def say_again(request: Empty) -> OkReply:
    print(request)
    return OkReply()


if __name__ == "__main__":
    app = FastGRPC()
    app.add_service(srv)
    app.run()
