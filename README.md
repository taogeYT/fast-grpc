# fast-grpc
Fast to Code gRPC in Python 3.7+

# Installation
Require Python 3.7+
```shell
pip install python-fast-grpc
```

# Quick start
1. Run a gRPC application
```python
from fast_grpc import BaseSchema, FastGRPC, ServicerContext, method

app = FastGRPC()

class HelloRequest(BaseSchema):
    name: str

class HelloReply(BaseSchema):
    message: str

class Greeter:
    @method("SayHello", request_model=HelloRequest, response_model=HelloReply)
    async def say_hello(self, request: HelloRequest, context: ServicerContext) -> HelloReply:
        return HelloReply(message=f"Greeter SayHello {request.name}")

app.add_service(Greeter)
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
