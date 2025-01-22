import inspect
from enum import Enum
from pathlib import Path
from typing import (
    Dict,
    Type,
    Optional,
    Callable,
    Union,
    AsyncIterator,
    TypeVar,
    AsyncIterable,
    AsyncGenerator,
)

from logzero import logger
from pydantic import BaseModel
import grpc
from abc import ABC, abstractmethod
from google.protobuf.message import Message

from fast_grpc.context import ServiceContext
from fast_grpc.utils import (
    dict_to_message,
    import_proto_file,
    get_typed_signature,
    snake_to_camel,
    get_param_annotation_model,
    message_to_str,
    message_to_pydantic,
    pydantic_to_message,
)

T = TypeVar("T")
R = TypeVar("R")


class MethodMode(Enum):
    UNARY_UNARY = "unary_unary"
    UNARY_STREAM = "unary_stream"
    STREAM_UNARY = "stream_unary"
    STREAM_STREAM = "stream_stream"


class BaseMethod(ABC):
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
        self.name = name or snake_to_camel(endpoint.__name__)
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
                    yield message_to_pydantic(item, self.request_model)

            values[self.request_param.name] = validate_async_iterator_request()
        else:
            values[self.request_param.name] = message_to_pydantic(
                request, self.request_model
            )
        return values

    def serialize_response(self, response, context):
        if isinstance(response, context.output_type):
            return response

        if self.response_model:
            validated_response = self.response_model.model_validate(response)
            return pydantic_to_message(validated_response, context.output_type)
        if isinstance(response, dict):
            return dict_to_message(response, context.output_type)
        return response


class UnaryUnaryMethod(BaseMethod):
    mode = MethodMode.UNARY_UNARY

    async def __call__(
        self, request: Union[Message, AsyncIterable[Message]], context: ServiceContext
    ) -> Message:
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
                f"GRPC invoke {context.service_method.name}({message_to_str(request)}) [Err] -> {repr(e)}"
            )
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise


class StreamUnaryMethod(UnaryUnaryMethod):
    mode = MethodMode.STREAM_UNARY


class UnaryStreamMethod(BaseMethod):
    mode = MethodMode.UNARY_STREAM

    async def __call__(
        self, request: Union[Message, AsyncIterable[Message]], context: ServiceContext
    ) -> AsyncGenerator[Message, None]:
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
                f"GRPC invoke {context.service_method.name}({message_to_str(request)}) [Err] -> {repr(e)}"
            )
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise


class StreamStreamMethod(UnaryStreamMethod):
    mode = MethodMode.STREAM_STREAM


MethodType = Union[
    UnaryUnaryMethod, UnaryStreamMethod, StreamUnaryMethod, StreamStreamMethod
]


class BaseService(ABC):
    """Base class for all gRPC services"""

    def __init__(self, name: str):
        """
        Args:
            name: your grpc service name.
        """
        self.name: str = name
        self.methods: Dict[str, MethodType] = {}
        self.grpc_servicer = None

    @abstractmethod
    def import_pb_modules(self):
        """Import or return pb2 and pb2_grpc modules"""
        pass

    @property
    def interface_name(self):
        return f"{self.name}Servicer"

    @property
    @abstractmethod
    def full_name(self) -> str:
        """Return the unique identifier of the service"""
        pass

    def __str__(self):
        return f"{self.__class__.__name__}(name={self.full_name})"

    def copy(self):
        return self.__class__(self.name)

    def add_method(
        self,
        endpoint: Callable,
        *,
        name: Optional[str] = None,
        method_class: Type[MethodType] = UnaryUnaryMethod,
        **kwargs,
    ) -> MethodType:
        method = method_class(name=name, endpoint=endpoint, **kwargs)
        self.methods[method.name] = method
        return method

    def unary_unary(
        self,
        name: Optional[str] = None,
        *,
        request_model: Optional[Type[BaseModel]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        description: str = "",
    ):
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
        name: Optional[str] = None,
        *,
        request_model: Optional[Type[BaseModel]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        description: str = "",
    ):
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
        name: Optional[str] = None,
        *,
        request_model: Optional[Type[BaseModel]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        description: str = "",
    ):
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
        name: Optional[str] = None,
        *,
        request_model: Optional[Type[BaseModel]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        description: str = "",
    ):
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

    def add_to_server(self, server):
        if self.grpc_servicer is not None:
            logger.info("Service already bound to server")
            return None

        if not self.methods:
            logger.info(f"{self} add_to_server [Ignored] -> no methods")
            return None

        pb2, pb2_grpc = self.import_pb_modules()
        interface_class = getattr(pb2_grpc, self.interface_name)
        self.grpc_servicer = make_grpc_service_from_methods(
            pb2, self.name, interface_class, self.methods
        )
        pb2_grpc_add_func = getattr(pb2_grpc, f"add_{self.interface_name}_to_server")
        pb2_grpc_add_func(self.grpc_servicer(), server)
        logger.info(f"{self} add_to_server success")


class Service(BaseService):
    """Service implementation using proto file"""

    def __init__(self, name: str, proto: str = ""):
        """
        Args:
            name: your grpc service name.
            proto: grpc proto file path.
        """
        super().__init__(name)
        if proto and not proto.endswith(".proto"):
            raise ValueError("Service proto must end with '.proto'")
        self.proto: str = proto

    def import_pb_modules(self):
        return import_proto_file(Path(self.proto))

    @property
    def full_name(self):
        return f"{self.proto}:{self.name}"

    def copy(self):
        return self.__class__(self.name, self.proto)


class Pb2Service(BaseService):
    """Service implementation using pb2 modules"""

    def __init__(self, name: str, pb2_module, pb2_grpc_module):
        """
        Args:
            name: your grpc service name
            pb2_module: the pb2 module containing your service definitions
            pb2_grpc_module: the pb2_grpc module containing your service implementations
        """
        super().__init__(name)
        self.pb2_module = pb2_module
        self.pb2_grpc_module = pb2_grpc_module

    def import_pb_modules(self):
        return self.pb2_module, self.pb2_grpc_module

    @property
    def full_name(self):
        return f"{self.pb2_module.__name__}:{self.name}"

    def copy(self):
        return self.__class__(self.name, self.pb2_module, self.pb2_grpc_module)


def make_grpc_service_from_methods(
    pb2,
    service_name,
    interface_class,
    methods: Dict[str, MethodType],
):
    def create_method(method: MethodType):
        if method.name not in service_descriptor.methods_by_name:
            raise RuntimeError(f"Method '{method.name}' not found")
        method_descriptor = service_descriptor.methods_by_name[method.name]
        method.name = f"{service_descriptor.full_name}.{method_descriptor.name}"
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
        {name: create_method(method) for name, method in methods.items()},
    )
