from pydantic import BaseModel

from fast_grpc import FastGRPC

app = FastGRPC(name="Greeter", proto="greeter.proto")


class HelloRequest(BaseModel):
    name: str


class HelloReply(BaseModel):
    message: str


@app.unary_unary()
async def say_hello(request: HelloRequest) -> HelloReply:
    return HelloReply(message=f"Hello {request.name}")


if __name__ == "__main__":
    app.run()
