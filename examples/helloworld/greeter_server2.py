from fast_grpc import BaseSchema, FastGRPC, ServicerContext, method


class HelloRequest(BaseSchema):
    name: str


class HelloReply(BaseSchema):
    message: str


class Greeter:
    @method("SayHello", request_model=HelloRequest, response_model=HelloReply)
    async def say_hello(self, request: HelloRequest, context: ServicerContext) -> HelloReply:
        return HelloReply(message=f"Greeter SayHello {request.name}")


if __name__ == "__main__":
    app = FastGRPC()
    app.add_service(Greeter)
    app.run()
