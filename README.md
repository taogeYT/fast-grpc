# FastGRPC
🚀 Build gRPC services in Python 3.9+ as easily as FastAPI.

## Installation
Require Python 3.9+
```shell
pip install python-fast-grpc
```

## A Simple Example
Define a gRPC service:
```python
from pydantic import BaseModel
from fast_grpc import FastGRPC

app = FastGRPC()

class HelloRequest(BaseModel):
    name: str

class HelloReply(BaseModel):
    message: str

@app.unary_unary()
async def say_hello(request: HelloRequest) -> HelloReply:
    return HelloReply(message=f"Greeter SayHello {request.name}")

if __name__ == '__main__':
    app.run()
```
Client Test:
```python
import grpc
import fast_grpc_pb2 as pb2
import fast_grpc_pb2_grpc as pb2_grpc

channel = grpc.insecure_channel("127.0.0.1:50051")
stub = pb2_grpc.FastGRPCStub(channel)
response = stub.SayHello(pb2.HelloRequest(name="FastGRPC"))
print("Client received: ", response)
```
## Use Middleware
```python
@app.middleware()
async def middleware(call_next, request, context):
    print("before request")
    response = await call_next(request, context)
    print("after request")
    return response

@app.middleware(is_server_streaming=True)
async def middleware(call_next, request, context):
    print("before streaming request")
    async for response in call_next(request, context):
        yield response
    print("after streaming request")
```
## Service
Use Service for modular design, similar to FastAPI's router.
```python
from fast_grpc import Service
srv = Service(name="Greeter")

@srv.unary_unary()
async def say_again(request: HelloRequest) -> HelloReply:
    return HelloReply(message=f"Greeter SayHello {request.name}")
```
## Pb2Service
Use Pb2Service if you're working with generated *_pb2.py and *_pb2_grpc.py files.
```python
import greeter_pb2
import greeter_pb2_grpc
srv = Pb2Service("Greeter", pb2_module=greeter_pb2, pb2_grpc_module=greeter_pb2_grpc)

@srv.unary_unary()
async def say_again(request: HelloRequest) -> HelloReply:
    return HelloReply(message=f"Greeter SayHello {request.name}")
```
## Generate Clients Using Pydantic
Automatically generate a Pydantic-based gRPC client from .proto files:
```python
from fast_grpc.proto import proto_to_python_client
proto_to_python_client("fast_grpc.proto")
```
