from fast_grpc import BaseSchema, FastGRPC

rpc = FastGRPC("Greeter")


class HelloRequest(BaseSchema):
    name: str


class HelloReply(BaseSchema):
    message: str


@rpc.add_method("SayHello", request_model=HelloRequest, response_model=HelloReply)
async def say_hello(request: HelloRequest) -> HelloReply:
    return HelloReply(message=f"Hello {request.name}")


if __name__ == "__main__":
    rpc.run()
