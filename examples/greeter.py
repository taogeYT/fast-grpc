from pydantic import BaseModel
from fast_grpc import FastGRPC

app = FastGRPC(service_name="Greeter", proto="greeter.proto")


class HelloRequest(BaseModel):
    name: str


class HelloReply(BaseModel):
    message: str


@app.unary_unary()
async def say_hello(request: HelloRequest) -> HelloReply:
    return HelloReply(message=f"Hello {request.name}")


if __name__ == "__main__":
    """
    import grpc
    import greeter_pb2 as pb2
    import greeter_pb2_grpc as pb2_grpc
    channel = grpc.insecure_channel("127.0.0.1:50051")
    stub = pb2_grpc.GreeterStub(channel)
    response = stub.SayHello(pb2.HelloRequest(name="fastGRPC"))
    print("Greeter client received: ", response)
    """
    app.run()
