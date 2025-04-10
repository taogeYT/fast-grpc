from pydantic import BaseModel

import greeter_pb2
import greeter_pb2_grpc
from fast_grpc import FastGRPC, Pb2Service

app = FastGRPC()
srv = Pb2Service("Greeter", pb2_module=greeter_pb2, pb2_grpc_module=greeter_pb2_grpc)


class HelloRequest(BaseModel):
    name: str


class HelloReply(BaseModel):
    message: str


@srv.unary_unary()
async def say_hello(request: HelloRequest) -> HelloReply:
    return HelloReply(message=f"Hello {request.name} with Pb2Service")


if __name__ == "__main__":
    app.add_service(srv)
    app.run()
