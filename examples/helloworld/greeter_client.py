import grpc

import greeter_pb2 as pb2
import greeter_pb2_grpc as pb2_grpc

channel = grpc.insecure_channel("127.0.0.1:50051")
stub = pb2_grpc.GreeterStub(channel)
response = stub.SayHello(pb2.HelloRequest(name="fastGRPC"))
print("Greeter client received: ", response)
