import inspect
import typing
from typing import Dict, Type, Optional, Callable, Union, AsyncIterator, Generic, TypeVar, AsyncGenerator

from logzero import logger
from pydantic import BaseModel
import grpc
from abc import ABC, abstractmethod

from fast_grpc.context import ServiceContext
from fast_grpc.proto import protoc_compile
from fast_grpc.types import Request, Response
from fast_grpc.utils import message_to_dict, dict_to_message, import_proto_file, get_typed_signature, to_pascal_case

T = TypeVar('T')
R = TypeVar('R')


class BaseMethod(ABC, Generic[Request, Response]):
    def __init__(
        self,
        endpoint: Callable,
        *,
        name: Optional[str] = None,
        request_model: Optional[Type[BaseModel]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        description: str = ""
    ):
        self.name = name or to_pascal_case(endpoint.__name__)
        self.endpoint = endpoint
        self.request_model = request_model
        self.response_model = response_model
        self.description = description
        endpoint_signature = get_typed_signature(self.endpoint)
        if 0< len(endpoint_signature.parameters) <= 2:
            request, *keys = endpoint_signature.parameters.keys()
            self.request_param = endpoint_signature.parameters[request]
            self.context_param = endpoint_signature.parameters[keys[0]] if keys else None
            if self.request_param.annotation is not inspect.Signature.empty:
                self.request_model = self.request_model or self.request_param.annotation
            if endpoint_signature.return_annotation is not inspect.Signature.empty:
                self.response_model = self.response_model or endpoint_signature.return_annotation
        else:
            raise NotImplementedError("service method only supports 2 parameters")

    @abstractmethod
    async def handle(self, request: Request, context: ServiceContext) -> Response:
        """处理请求"""
        pass

    @abstractmethod
    def get_service_method(self) -> grpc.RpcMethodHandler:
        """获取 gRPC 服务方法处理器"""
        pass

    def solve_params(self, request, context):
        values = {}
        if self.context_param:
            values[self.context_param.name] = context

        if not self.request_model:
            values[self.request_param.name] = request
            return values
        if isinstance(request, AsyncIterator):
            async def validate_async_iterator_request():
                async for item in request:
                    yield self.request_model.parse_obj(message_to_dict(item))
            values[self.request_param.name] = validate_async_iterator_request()
        else:
            values[self.request_param.name] = self.request_model.parse_obj(message_to_dict(request))
        return values

    def serialize_response(self, response, context):
        if isinstance(response, context.output_type):
            return response

        if self.response_model:
            validated_response = self.response_model.parse_obj(response)
            return dict_to_message(validated_response.dict(exclude_unset=True), context.output_type)
        if isinstance(response, dict):
            return dict_to_message(response, context.output_type)
        return response


class UnaryUnaryMethod(BaseMethod[Request, Response]):
    """一元调用方法"""

    async def handle(self, request: Request, context: ServiceContext) -> Response:
        try:
            values = self.solve_params(request, context)
            response = await self.endpoint(**values)
            return self.serialize_response(response, context)
        except Exception as e:
            logger.exception(e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise

    def get_service_method(self) -> grpc.RpcMethodHandler:
        return grpc.unary_unary_rpc_method_handler(
            self.handle,
            request_deserializer=None,
            response_serializer=None
        )


class UnaryStreamMethod(BaseMethod[Request, AsyncIterator[Response]]):
    """一元请求，流式响应方法"""

    async def handle(self, request: Request, context: ServiceContext) -> AsyncIterator[Response]:
        try:
            values = self.solve_params(request, context)
            iterator_response = await self.endpoint(**values)

            async for response in await iterator_response:
                yield self.serialize_response(response, context)

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise

    def get_service_method(self) -> grpc.RpcMethodHandler:
        return grpc.unary_stream_rpc_method_handler(
            self.handle,
            request_deserializer=None,
            response_serializer=None
        )


class StreamUnaryMethod(BaseMethod[AsyncIterator[Request], Response]):
    """流式请求，一元响应方法"""

    async def handle(self, request_iterator: AsyncIterator[Request], context: ServiceContext) -> Response:
        try:
            values = self.solve_params(request_iterator, context)
            response = await self.endpoint(**values)
            return self.serialize_response(response, context)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise

    def get_service_method(self) -> grpc.RpcMethodHandler:
        return grpc.stream_unary_rpc_method_handler(
            self.handle,
            request_deserializer=None,
            response_serializer=None
        )


class StreamStreamMethod(BaseMethod[AsyncIterator[Request], AsyncIterator[Response]]):
    """双向流式方法"""

    async def handle(self, request_iterator: AsyncIterator[Request], context: ServiceContext) -> AsyncIterator[Response]:
        try:
            values = self.solve_params(request_iterator, context)
            iterator_response = await self.endpoint(**values)
            async for response in await iterator_response:
                yield self.serialize_response(response, context)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise

    def get_service_method(self) -> grpc.RpcMethodHandler:
        return grpc.stream_stream_rpc_method_handler(
            self.handle,
            request_deserializer=None,
            response_serializer=None
        )


MethodType = Union[UnaryUnaryMethod, UnaryStreamMethod, StreamUnaryMethod, StreamStreamMethod]


class Service:
    def __init__(self, name: str, proto: typing.Optional[str] = None):
        self.name = name
        self.proto = proto
        self.methods: Dict[str, MethodType] = {}

    @property
    def interface_name(self):
        return f"{self.name}Servicer"

    def add_method(
            self,
            endpoint: Callable,
            *,
            name: Optional[str] = None,
            method_class: Type[MethodType] = UnaryUnaryMethod,
            **kwargs
    ) -> MethodType:
        """添加方法"""
        method = method_class(name=name, endpoint=endpoint, **kwargs)
        self.methods[method.name] = method
        return method

    def unary_unary(
        self,
        *,
        name: Optional[str] = None,
        request_model: Optional[Type[BaseModel]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        description: str = ""
    ):
        """一元调用装饰器"""

        def decorator(endpoint: Callable[[T], R]) -> Callable[[T], R]:
            self.add_method(
                name=name,
                endpoint=endpoint,
                method_class=UnaryUnaryMethod,
                request_model=request_model,
                response_model=response_model,
                description=description
            )
            return endpoint

        return decorator

    def unary_stream(
            self,
            *,
            name: Optional[str] = None,
            request_model: Optional[Type[BaseModel]] = None,
            response_model: Optional[Type[BaseModel]] = None,
            description: str = ""
    ):
        """一元请求，流式响应装饰器"""

        def decorator(endpoint: Callable[[T], AsyncIterator[R]]) -> Callable[[T], AsyncIterator[R]]:
            self.add_method(
                name=name,
                endpoint=endpoint,
                method_class=UnaryStreamMethod,
                request_model=request_model,
                response_model=response_model,
                description=description
            )
            return endpoint

        return decorator

    def stream_unary(
            self,
            *,
            name: Optional[str] = None,
            request_model: Optional[Type[BaseModel]] = None,
            response_model: Optional[Type[BaseModel]] = None,
            description: str = ""
    ):
        """流式请求，一元响应装饰器"""

        def decorator(endpoint: Callable[[AsyncIterator[T]], R]) -> Callable[[AsyncIterator[T]], R]:
            self.add_method(
                name=name,
                endpoint=endpoint,
                method_class=StreamUnaryMethod,
                request_model=request_model,
                response_model=response_model,
                description=description
            )
            return endpoint

        return decorator

    def stream_stream(
            self,
            *,
            name: Optional[str] = None,
            request_model: Optional[Type[BaseModel]] = None,
            response_model: Optional[Type[BaseModel]] = None,
            description: str = ""
    ):
        """双向流式装饰器"""

        def decorator(
                endpoint: Callable[[AsyncIterator[T]], AsyncIterator[R]]
        ) -> Callable[[AsyncIterator[T]], AsyncIterator[R]]:
            self.add_method(
                name=name,
                endpoint=endpoint,
                method_class=StreamStreamMethod,
                request_model=request_model,
                response_model=response_model,
                description=description
            )
            return endpoint

        return decorator

    def get_grpc_servicer(self, pb2, interface_class):
        srv_cls = make_grpc_service_from_methods(pb2, self.name, interface_class, self.methods)
        return srv_cls


def make_grpc_service_from_methods(pb2, service_name, interface_class, methods: Dict[str, MethodType]):
    def create_method(method: MethodType, method_descriptor):
        async def service_method(self, request, context):
            srv_context = ServiceContext(context, method_descriptor)
            return await method.handle(request, srv_context)

        service_method.__name__ = method.name
        return service_method

    service_descriptor = pb2.DESCRIPTOR.services_by_name[service_name]
    return type(
        service_name,
        (interface_class,),
        {
            name: create_method(method, service_descriptor.methods_by_name[name]) for name, method in methods.items()
        },
    )


def add_service_to_server(name, proto, services: typing.List[Service], server):
    methods = {}
    for srv in services:
        methods.update(srv.methods)
    if not methods:
        logger.info(f"Service add_service_to_server {name=} {proto=} [Ignored] -> no methods")
        return None
    protoc_compile(proto)
    interface_name = f"{name}Servicer"
    pb2, pb2_grpc = import_proto_file(proto)
    interface_class = getattr(pb2_grpc, interface_name)
    grpc_service = make_grpc_service_from_methods(pb2, name, interface_class, methods)
    pb2_grpc_add_func = getattr(pb2_grpc, f"add_{interface_name}_to_server")
    pb2_grpc_add_func(grpc_service(), server)
    logger.info(f"Service add_service_to_server {name=} {proto=}")
    return None
