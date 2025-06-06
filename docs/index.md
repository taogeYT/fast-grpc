# Overview
FastGRPC is a high-performance gRPC framework designed to simplify the development of gRPC services

## Features
- Fast to code: FastAPI-like API design
- Pure async: Built with async/await only
- Pydantic integration: Request/Response validation
- Auto Proto: Automatic .proto file generation
- Type hints: Full Python type annotations support

## Installation
Requires Python 3.9+
```shell
pip install python-fast-grpc
```

## Quick Start
Create a simple gRPC service:

```python
from pydantic import BaseModel
from fast_grpc import FastGRPC

# create a FastGRPC app
# name: defines the default service name in proto file
# proto: defines the default proto file path
# auto_gen_proto: if True, will automatically generate proto file from your code
#                if False, you need to provide your own proto file
app = FastGRPC(
    name="Greeter",  # default service name
    proto="greeter.proto",   # default proto file path
    auto_gen_proto=True      # auto generate proto file
)

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

Test with a client:
```python
import grpc
import greeter_pb2 as pb2
import greeter_pb2_grpc as pb2_grpc

channel = grpc.insecure_channel("127.0.0.1:50051")
stub = pb2_grpc.GreeterStub(channel)
response = stub.SayHello(pb2.HelloRequest(name="FastGRPC"))
print("Greeter client received: ", response)
```
Use Context:
```python
from fast_grpc import ServiceContext
@app.unary_unary()
async def unary_unary(request: HelloRequest, context: ServiceContext) -> HelloReply:
    print(context.metadata)
    return HelloReply(message=f"Hello {request.name}")
```

## Service Definition
FastGRPC supports define your gRPC methods in a single Service:

```python
from pydantic import BaseModel
from fast_grpc import FastGRPC, Service

app = FastGRPC()

class HelloRequest(BaseModel):
    name: str

class HelloReply(BaseModel):
    message: str

# Create a service with specific name and proto file
srv = Service(
    name="Greeter",        # service name in proto file
    proto="greeter.proto"  # proto file path for this service
)

@srv.unary_unary()
async def say_hello(request: HelloRequest) -> HelloReply:
    return HelloReply(message=f"Hello {request.name}")

if __name__ == '__main__':
    app.add_service(srv)  # add service to app
    app.run()
```

## Streaming Methods
FastGRPC supports grpc streaming methods:

### Unary-Unary
```python
@app.unary_unary()
async def unary_unary(request: HelloRequest) -> HelloReply:
    return HelloReply(message=f"Hello {request.name}")
```

### Stream-Unary
```python
@app.stream_unary()
async def stream_unary(request: AsyncIterator[HelloRequest]) -> HelloReply:
    response = HelloReply(message="SayHello:")
    async for message in request:
        response.message += f" {message.name}"
    return response
```

### Unary-Stream
```python
@app.unary_stream()
async def unary_stream(request: HelloRequest) -> AsyncIterator[HelloReply]:
    for i in range(3):
        yield HelloReply(message=f"SayHello: {request.name} {i}")
```

### Stream-Stream
```python
@app.stream_stream()
async def stream_stream(
    request: AsyncIterator[HelloRequest],
) -> AsyncIterator[HelloReply]:
    async for message in request:
        yield HelloReply(message=f"SayHello: {message.name}")
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

These examples demonstrate how to implement different types of gRPC streaming methods using FastGRPC. Each method is fully asynchronous, leveraging Python's `async` and `await` syntax for efficient I/O operations.
