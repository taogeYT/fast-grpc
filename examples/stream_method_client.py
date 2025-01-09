import grpc
import fast_grpc_pb2 as pb2
import fast_grpc_pb2_grpc as pb2_grpc


def request_iterator():
    for i in range(3):
        yield pb2.HelloRequest(name=f"FastGRPC {i}")


def unary_unary(stub):
    response = stub.UnaryUnary(pb2.HelloRequest(name="FastGRPC"))
    print("unary_unary Response: ", response.message)


def stream_unary(stub):
    response = stub.StreamUnary(request_iterator())
    print("stream_unary Response:", response.message)


def unary_stream(stub):
    response = stub.UnaryStream(pb2.HelloRequest(name="FastGRPC"))
    for message in response:
        print("unary_stream Response:", message.message)


def stream_stream(stub):
    response = stub.StreamStream(request_iterator())
    for message in response:
        print("stream_stream Response:", message.message)


def main():
    channel = grpc.insecure_channel("127.0.0.1:50051")
    stub = pb2_grpc.FastGRPCStub(channel)
    unary_unary(stub)
    stream_unary(stub)
    unary_stream(stub)
    stream_stream(stub)


if __name__ == "__main__":
    main()
