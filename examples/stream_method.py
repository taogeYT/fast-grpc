from typing import AsyncIterator
from pydantic import BaseModel
from fast_grpc import FastGRPC

app = FastGRPC()


class HelloRequest(BaseModel):
    name: str


class HelloReply(BaseModel):
    message: str


@app.unary_unary()
async def unary_unary(request: HelloRequest) -> HelloReply:
    return HelloReply(message=f"Hello {request.name}")


@app.stream_unary()
async def stream_unary(request: AsyncIterator[HelloRequest]) -> HelloReply:
    response = HelloReply(message="SayHello:")
    async for message in request:
        response.message += f" {message.name}"
    return response


@app.unary_stream()
async def unary_stream(request: HelloRequest) -> AsyncIterator[HelloReply]:
    for i in range(3):
        yield HelloReply(message=f"SayHello: {request.name} {i}")


@app.stream_stream()
async def stream_stream(
    request: AsyncIterator[HelloRequest],
) -> AsyncIterator[HelloReply]:
    async for message in request:
        yield HelloReply(message=f"SayHello: {message.name}")


if __name__ == "__main__":
    app.run()
