# fast-grpc
Fast to Code gRPC in Python 3.9+

# Installation
Require Python 3.9+
```shell
pip install python-fast-grpc
```

# Quick start
1. Run a gRPC application
```python
from pydantic import BaseModel
from fast_grpc import FastGRPC

app = FastGRPC(service_name="Greeter", proto="greeter.proto")

class HelloRequest(BaseModel):
    name: str

class HelloReply(BaseModel):
    message: str

@app.unary_unary()
async def say_hello(request: HelloRequest) -> HelloReply:
    return HelloReply(message=f"Greeter SayHello {request.name}")

# this step will generate .proto file and python gRPC code, then start a grpc server
app.run()
```
2. Client invoke
```python
import grpc
import greeter_pb2 as pb2
import greeter_pb2_grpc as pb2_grpc

channel = grpc.insecure_channel("127.0.0.1:50051")
stub = pb2_grpc.GreeterStub(channel)
response = stub.SayHello(pb2.HelloRequest(name="fastGRPC"))
print("Greeter client received: ", response)
```
