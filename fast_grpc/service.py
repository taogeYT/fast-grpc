import inspect
import typing
from enum import Enum
from pathlib import Path
from typing import (
    Dict,
    Type,
    Optional,
    Callable,
    Union,
    AsyncIterator,
    Generic,
    TypeVar,
)

from logzero import logger
from pydantic import BaseModel
import grpc
from abc import ABC, abstractmethod

from fast_grpc.context import ServiceContext
from fast_grpc.types import Request, Response
from fast_grpc.utils import (
    message_to_dict,
    dict_to_message,
    import_proto_file,
    get_typed_signature,
    to_pascal_case,
    json_to_message,
    get_param_annotation_model,
    message_to_str,
)

T = TypeVar("T")
R = TypeVar("R")


class MethodMode(Enum):
    UNARY_UNARY = "unary_unary"
    UNARY_STREAM = "unary_stream"
    STREAM_UNARY = "stream_unary"
    STREAM_STREAM = "stream_stream"


class BaseMethod(ABC, Generic[Request, Response]):
    mode: MethodMode

    def __init__(
        self,
        endpoint: Callable,
        *,
        name: Optional[str] = None,
        request_model: Optional[Type[BaseModel]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        description: str = "",
    ):
        self.name = name or to_pascal_case(endpoint.__name__)
        self.endpoint = endpoint
        self.request_model = request_model
        self.response_model = response_model
        self.description = description
        endpoint_signature = get_typed_signature(self.endpoint)
        if not (0 < len(endpoint_signature.parameters) <= 2):
            raise NotImplementedError("service method only supports 2 parameters")
        request, *keys = endpoint_signature.parameters.keys()
        self.request_param = endpoint_signature.parameters[request]
        self.context_param = endpoint_signature.parameters[keys[0]] if keys else None
        if self.request_param.annotation is not inspect.Signature.empty:
            request_param_model = get_param_annotation_model(
                self.request_param.annotation, self.is_request_iterable
            )
            self.request_model = self.request_model or request_param_model
        if endpoint_signature.return_annotation is not inspect.Signature.empty:
            response_param_model = get_param_annotation_model(
                endpoint_signature.return_annotation, self.is_response_iterable
            )
            self.response_model = self.response_model or response_param_model
        if self.response_model and not issubclass(self.response_model, BaseModel):
            raise ValueError("response_model must be a BaseModel subclass")
        if self.response_model and not issubclass(self.response_model, BaseModel):
            raise ValueError("response_model must be a BaseModel subclass")

    @property
    def is_request_iterable(self):
        return self.mode in (MethodMode.STREAM_UNARY, MethodMode.STREAM_STREAM)

    @property
    def is_response_iterable(self):
        return self.mode in (MethodMode.UNARY_STREAM, MethodMode.STREAM_STREAM)

    def _parse_request_param(self, param_annotation):
        if param_annotation is inspect.Signature.empty:
            return None
        if self.mode in {MethodMode.STREAM_UNARY, MethodMode.STREAM_STREAM}:
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
                    yield self.request_model.model_validate(message_to_dict(item))

            values[self.request_param.name] = validate_async_iterator_request()
        else:
            values[self.request_param.name] = self.request_model.model_validate(
                message_to_dict(request)
            )
        return values

    def serialize_response(self, response, context):
        if isinstance(response, context.output_type):
            return response

        if self.response_model:
            validated_response = self.response_model.model_validate(response)
            return json_to_message(
                validated_response.model_dump_json(),
                context.output_type,
            )
        if isinstance(response, dict):
            return dict_to_message(response, context.output_type)
        return response

    @abstractmethod
    async def __call__(self, request: Request, context: ServiceContext) -> Response:
        pass


class UnaryUnaryMethod(BaseMethod[Request, Response]):
    mode = MethodMode.UNARY_UNARY

    async def __call__(self, request: Request, context: ServiceContext) -> Response:
        try:
            values = self.solve_params(request, context)
            result = await self.endpoint(**values)
            response = self.serialize_response(result, context)
            logger.info(
                f"GRPC invoke {context.service_method.name}({message_to_str(request)}) [OK] {context.elapsed_time} ms"
            )
            return response
        except Exception as e:
            logger.exception(
                f"GRPC invoke {context.service_method.__name__}({message_to_str(request)}) [Err] -> {repr(e)}"
            )
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise

    def get_service_method(self) -> grpc.RpcMethodHandler:
        return grpc.unary_unary_rpc_method_handler(
            self.__call__, request_deserializer=None, response_serializer=None
        )


class UnaryStreamMethod(BaseMethod[Request, AsyncIterator[Response]]):
    mode = MethodMode.UNARY_STREAM

    async def __call__(
        self, request: Request, context: ServiceContext
    ) -> AsyncIterator[Response]:
        try:
            values = self.solve_params(request, context)
            iterator_response = self.endpoint(**values)
            async for response in iterator_response:
                yield self.serialize_response(response, context)
            logger.info(
                f"GRPC invoke {context.service_method.name}({message_to_str(request)}) [OK] {context.elapsed_time} ms"
            )
        except Exception as e:
            logger.exception(
                f"GRPC invoke {context.service_method.__name__}({message_to_str(request)}) [Err] -> {repr(e)}"
            )
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise

    def get_service_method(self) -> grpc.RpcMethodHandler:
        return grpc.unary_stream_rpc_method_handler(
            self.__call__, request_deserializer=None, response_serializer=None
        )


class StreamUnaryMethod(BaseMethod[AsyncIterator[Request], Response]):
    mode = MethodMode.STREAM_UNARY

    async def __call__(
        self, request_iterator: AsyncIterator[Request], context: ServiceContext
    ) -> Response:
        try:
            values = self.solve_params(request_iterator, context)
            response = await self.endpoint(**values)
            result = self.serialize_response(response, context)
            logger.info(
                f"GRPC invoke {context.service_method.name}({message_to_str(request_iterator)}) [OK] {context.elapsed_time} ms"
            )
            return result
        except Exception as e:
            logger.exception(
                f"GRPC invoke {context.service_method.__name__}({message_to_str(request_iterator)}) [Err] -> {repr(e)}"
            )
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise

    def get_service_method(self) -> grpc.RpcMethodHandler:
        return grpc.stream_unary_rpc_method_handler(
            self.__call__, request_deserializer=None, response_serializer=None
        )


class StreamStreamMethod(BaseMethod[AsyncIterator[Request], AsyncIterator[Response]]):
    mode = MethodMode.STREAM_STREAM

    async def __call__(
        self, request_iterator: AsyncIterator[Request], context: ServiceContext
    ) -> AsyncIterator[Response]:
        try:
            values = self.solve_params(request_iterator, context)
            iterator_response = self.endpoint(**values)
            async for response in iterator_response:
                yield self.serialize_response(response, context)
            logger.info(
                f"GRPC invoke {context.service_method.name}({message_to_str(request_iterator)}) [OK] {context.elapsed_time} ms"
            )
        except Exception as e:
            logger.exception(
                f"GRPC invoke {context.service_method.__name__}({message_to_str(request_iterator)}) [Err] -> {repr(e)}"
            )
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise

    def get_service_method(self) -> grpc.RpcMethodHandler:
        return grpc.stream_stream_rpc_method_handler(
            self.__call__, request_deserializer=None, response_serializer=None
        )


MethodType = Union[
    UnaryUnaryMethod, UnaryStreamMethod, StreamUnaryMethod, StreamStreamMethod
]


class Service:
    def __init__(self, name: str, proto: str = ""):
        if proto and not proto.endswith(".proto"):
            raise ValueError("Service proto must end with '.proto'")
        self.name: str = name
        self.proto: str = proto
        self.methods: Dict[str, MethodType] = {}
        self.grpc_servicer = None

    @property
    def interface_name(self):
        return f"{self.name}Servicer"

    @property
    def proto_path(self):
        return Path(self.proto)

    def add_method(
        self,
        endpoint: Callable,
        *,
        name: Optional[str] = None,
        method_class: Type[MethodType] = UnaryUnaryMethod,
        **kwargs,
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
        description: str = "",
    ):
        """一元调用装饰器"""

        def decorator(endpoint: Callable[[T], R]) -> Callable[[T], R]:
            self.add_method(
                name=name,
                endpoint=endpoint,
                method_class=UnaryUnaryMethod,
                request_model=request_model,
                response_model=response_model,
                description=description,
            )
            return endpoint

        return decorator

    def unary_stream(
        self,
        *,
        name: Optional[str] = None,
        request_model: Optional[Type[BaseModel]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        description: str = "",
    ):
        """一元请求，流式响应装饰器"""

        def decorator(
            endpoint: Callable[[T], AsyncIterator[R]],
        ) -> Callable[[T], AsyncIterator[R]]:
            self.add_method(
                name=name,
                endpoint=endpoint,
                method_class=UnaryStreamMethod,
                request_model=request_model,
                response_model=response_model,
                description=description,
            )
            return endpoint

        return decorator

    def stream_unary(
        self,
        *,
        name: Optional[str] = None,
        request_model: Optional[Type[BaseModel]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        description: str = "",
    ):
        """流式请求，一元响应装饰器"""

        def decorator(
            endpoint: Callable[[AsyncIterator[T]], R],
        ) -> Callable[[AsyncIterator[T]], R]:
            self.add_method(
                name=name,
                endpoint=endpoint,
                method_class=StreamUnaryMethod,
                request_model=request_model,
                response_model=response_model,
                description=description,
            )
            return endpoint

        return decorator

    def stream_stream(
        self,
        *,
        name: Optional[str] = None,
        request_model: Optional[Type[BaseModel]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        description: str = "",
    ):
        """双向流式装饰器"""

        def decorator(
            endpoint: Callable[[AsyncIterator[T]], AsyncIterator[R]],
        ) -> Callable[[AsyncIterator[T]], AsyncIterator[R]]:
            self.add_method(
                name=name,
                endpoint=endpoint,
                method_class=StreamStreamMethod,
                request_model=request_model,
                response_model=response_model,
                description=description,
            )
            return endpoint

        return decorator

    def bind_server(self, server):
        if self.grpc_servicer is not None:
            logger.info("Service already bound to server")
            return None
        name = self.name
        proto = self.proto_path
        methods = self.methods
        if not methods:
            logger.info(f"Service bind_server {name=} {proto=} [Ignored] -> no methods")
            return None
        interface_name = f"{name}Servicer"
        pb2, pb2_grpc = import_proto_file(proto)
        interface_class = getattr(pb2_grpc, interface_name)
        self.grpc_servicer = make_grpc_service_from_methods(
            pb2, name, interface_class, methods
        )
        pb2_grpc_add_func = getattr(pb2_grpc, f"add_{interface_name}_to_server")
        pb2_grpc_add_func(self.grpc_servicer(), server)
        logger.info(f"Service bind_server {name=} {proto=} [Success]")


def make_grpc_service_from_methods(
    pb2,
    service_name,
    interface_class,
    methods: Dict[str, MethodType],
):
    def create_method(method: MethodType, method_descriptor):
        if method.is_response_iterable:

            async def service_iterable_method(self, request, context):
                srv_context = ServiceContext(context, method, method_descriptor)
                async for response in method(request, srv_context):
                    yield response

            service_iterable_method.__name__ = method.name
            return service_iterable_method
        else:

            async def service_method(self, request, context):
                srv_context = ServiceContext(context, method, method_descriptor)
                return await method(request, srv_context)

            service_method.__name__ = method.name
            return service_method

    service_descriptor = pb2.DESCRIPTOR.services_by_name[service_name]
    return type(
        service_name,
        (interface_class,),
        {
            name: create_method(method, service_descriptor.methods_by_name[name])
            for name, method in methods.items()
        },
    )


class Servicer:
    @classmethod
    def as_service(cls, proto: typing.Optional[str] = None):
        pass
