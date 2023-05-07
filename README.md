# fast-grpc
fast to code grpc in Python 3.9+

# Installation
Require Python 3.9+
```shell
pip install python-fast-grpc
```

# Quick start
1. Run a gRPC application
```python
from fast_grpc import BaseSchema, FastGRPC

rpc = FastGRPC("Greeter")

class HelloRequest(BaseSchema):
    name: str

class HelloReply(BaseSchema):
    message: str

@rpc.add_method("SayHello", request_model=HelloRequest, response_model=HelloReply)
async def say_hello(request: HelloRequest) -> HelloReply:
    return HelloReply(message=f"Hello {request.name}")

# this step will generate .proto file and python gRPC code, then start a grpc server
rpc.run()
```
2. run client invoke
```python
import grpc
import greeter_pb2 as pb2
import greeter_pb2_grpc as pb2_grpc

channel = grpc.insecure_channel("127.0.0.1:50051")
stub = pb2_grpc.GreeterStub(channel)
response = stub.SayHello(pb2.HelloRequest(name="fastGRPC"))
print("Greeter client received: ", response)
```
