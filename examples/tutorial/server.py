# -*- coding: utf-8 -*-
from tutorial.schema import Data, HelloReply, HelloRequest, Language, OkReply

from fast_grpc import FastGRPC
from fast_grpc.types import Empty

rpc = FastGRPC("Tutorial")


@rpc.add_method("SayHello", request_model=HelloRequest, response_model=HelloReply)
async def say_hello(request: HelloRequest) -> HelloReply:
    return HelloReply(
        message=f"hello {request.name}", data=Data(name="grpc", value=1, age=18), language=Language.LANGUAGE_ZH
    )


@rpc.add_method("SayHello2", request_model=Empty, response_model=OkReply)
async def say_hello2(request: Empty) -> OkReply:
    print(request)
    return OkReply.parse_obj({})


if __name__ == "__main__":
    rpc.run()
