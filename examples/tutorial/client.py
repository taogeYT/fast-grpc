# -*- coding: utf-8 -*-
import google.protobuf.empty_pb2 as empty_pb2
import grpc
import tutorial.tutorial_pb2 as pb2
import tutorial.tutorial_pb2_grpc as pb2_grpc

# 连接 rpc 服务器
channel = grpc.insecure_channel("127.0.0.1:50051")
# 调用 rpc 服务
stub = pb2_grpc.TutorialStub(channel)
response = stub.SayHello(pb2.HelloRequest(name="hello fast rpc"))
print("Greeter client received: ", response)

response = stub.SayHello2(empty_pb2.Empty())
print("Greeter client received: ", response)
