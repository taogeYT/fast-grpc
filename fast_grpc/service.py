# -*- coding: utf-8 -*-
import inspect
import os
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from typing import Any, Callable, List, Optional

from google.protobuf.json_format import MessageToDict, Parse, ParseDict

from fast_grpc.proto import ProtoBuilder, protoc_compile
from fast_grpc.types import Message, ServicerContext
from fast_grpc.utils import (
    await_sync_function,
    camel_to_snake,
    is_camel_case,
    is_snake_case,
)


def message_to_dict(message):
    return MessageToDict(message, including_default_value_fields=True, preserving_proto_field_name=True)


def json_to_message(data, message):
    return Parse(data, message, ignore_unknown_fields=True)


def dict_to_message(data, message):
    return ParseDict(data, message, ignore_unknown_fields=True)


class ServiceMetaclass(type):
    def __new__(mcs, name, bases, attrs):
        new_class = type.__new__(mcs, name, bases, attrs)
        for key, value in attrs.items():
            setattr(new_class, key, value)

        return new_class


class Service:
    def __init__(self, service_name: str, package_name: str = "", proto_path="."):
        self.service_name = service_name
        self.methods: List[Method] = []
        self.proto_path = proto_path
        self.thread_pool: Optional[ThreadPoolExecutor] = None

        if is_camel_case(self.service_name):
            self.proto_name = camel_to_snake(self.service_name).lower()
        elif is_snake_case(self.service_name):
            self.proto_name = self.service_name.lower()
        else:
            self.proto_name = self.service_name.lower()

        if package_name:
            self.package_name = package_name
        else:
            self.package_name = self.proto_name

        self._proto_file = None
        self._pb2 = None
        self._pb2_grpc = None

    @property
    def proto_file(self):
        if self._proto_file is None:
            if not os.path.exists(self.proto_path):
                os.makedirs(self.proto_path)
            self._proto_file = os.path.join(self.proto_path, f"{self.proto_name}.proto")
        return self._proto_file

    @property
    def pb2(self):
        if self._pb2 is None:
            self._pb2 = import_module(f"{self.package_name}_pb2")
        return self._pb2

    @property
    def pb2_grpc(self):
        if self._pb2_grpc is None:
            self._pb2_grpc = import_module(f"{self.package_name}_pb2_grpc")
        return self._pb2_grpc

    def gen_and_compile_proto(self):
        builder = ProtoBuilder(self)
        proto = builder.create()
        with open(self.proto_file, "w") as f:
            f.write(proto)
        protoc_compile(self.proto_file)

    def bind_server(self, server, app):
        """
        demo_pb2_grpc.add_GreeterServicer_to_server(Greeter(), server)
        """
        getattr(self.pb2_grpc, f"add_{self.service_name}Servicer_to_server")(self.to_grpc_service(app), server)
        # self.thread_pool

    def to_grpc_service(self, app):
        def decorator(method: Method):
            async def handle(_self, request, context):
                return await app(request, context, method)

            return handle

        service_interface = getattr(self.pb2_grpc, f"{self.service_name}Servicer")
        attrs_dict = {method.name: decorator(method) for method in self.methods}
        return type(f"{self.service_name}", (service_interface,), attrs_dict)()

    def add_rpc_method(
        self,
        name: str,
        endpoint: Callable[..., Any],
        *,
        request_model: Any,
        response_model: Any,
    ):
        self.methods.append(
            Method(
                name=name, endpoint=endpoint, request_model=request_model, response_model=response_model, service=self
            )
        )

    async def __call__(self, request: Message, context: ServicerContext, invoke_method: "Method") -> Message:
        py_request = invoke_method.request_model.parse_obj(message_to_dict(request))
        response = await invoke_method(py_request, context)
        return json_to_message(response.json(), getattr(self.pb2, invoke_method.response_model.__name__)())


class Method:
    def __init__(
        self,
        name: str,
        endpoint: Callable[..., Any],
        *,
        request_model: Any,
        response_model: Any,
        service: Service,
    ):
        self.name = name
        self.endpoint = endpoint
        self.request_model = request_model
        self.response_model = response_model
        self.service = service

    async def __call__(self, request, context):
        if inspect.isasyncgenfunction(self.endpoint):
            raise NotImplementedError(f"{self.endpoint} is an async generator function, which is not supported.")
        elif inspect.iscoroutinefunction(self.endpoint):
            response = await self.endpoint(request)
            return response
        else:
            response = await await_sync_function(self.endpoint)(request)
            return response
