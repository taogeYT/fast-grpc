# -*- coding: utf-8 -*-
import asyncio
from pathlib import Path
from typing import Callable, Optional, Type

import grpc
from grpc.aio import Server
from grpc.aio._typing import ChannelArgumentType  # noqa
from grpc_reflection.v1alpha import reflection
from logzero import logger
from pydantic import BaseModel

from fast_grpc.middleware import ServerErrorMiddleware, ServerStreamingErrorMiddleware
from fast_grpc.proto import ProtoBuilder
from fast_grpc.service import (
    BaseService,
    Service,
    StreamStreamMethod,
    StreamUnaryMethod,
    UnaryStreamMethod,
    UnaryUnaryMethod,
)
from fast_grpc.types import ProtoTag
from fast_grpc.utils import protoc_compile


class FastGRPC(object):
    """
    `FastGRPC` app class, the main entrypoint to use FastGRPC.

    ## Example

    ```python
    from fast_grpc import FastGRPC

    app = FastGRPC(name="Greeter", proto="greeter.proto")
    ```
    """

    def __init__(
        self,
        *,
        name: str = "FastGRPC",
        proto: str = "fast_grpc.proto",
        auto_gen_proto: bool = True,
        type_mapping: Optional[dict[type, ProtoTag]] = None,
        compile_proto: bool = True,
        generate_mypy: bool = False,
    ):
        """
        Args:
            name: default grpc service name.
            proto: grpc proto file path.
            auto_gen_proto: Whether to automatically generate proto file or not. if not, the proto file will be defined by yourself.
            type_mapping: custom type mapping.
            compile_proto: Whether to compile proto file or not.
            generate_mypy: Whether to generate mypy stubs or not.
        """
        self.service = Service(name=name, proto=proto)
        self._services: dict[str, Service] = {f"{proto}:{name}": self.service}
        self._auto_gen_proto = auto_gen_proto
        self._middlewares: list[Callable] = [ServerErrorMiddleware()]
        self._server_streaming_middlewares: list[Callable] = [
            ServerStreamingErrorMiddleware()
        ]
        self._type_mapping = type_mapping
        self._compile_proto = compile_proto
        self._generate_mypy = generate_mypy

    def setup(self) -> None:
        builders = {}
        for service in self._services.values():
            if not service.methods or not isinstance(service, Service):
                continue
            path = Path(service.proto)
            if path not in builders:
                builders[path] = ProtoBuilder(
                    package=path.stem, type_mapping=self._type_mapping
                )
            builders[path].add_service(service)
        for proto, builder in builders.items():
            if self._auto_gen_proto:
                proto_define = builder.get_proto()
                content = proto_define.render_proto_file()
                proto.parent.mkdir(parents=True, exist_ok=True)
                proto.write_text(content)
                logger.info(f"Created {proto} file success")
            if self._compile_proto:
                protoc_compile(proto, generate_mypy=self._generate_mypy)

    def add_middleware(self, middleware: Callable, is_server_streaming=False) -> None:
        if is_server_streaming:
            self._server_streaming_middlewares.append(middleware)
        else:
            self._middlewares.append(middleware)

    def middleware(self, is_server_streaming=False):
        def decorator(func: Callable) -> Callable:
            self.add_middleware(func, is_server_streaming)
            return func

        return decorator

    def unary_unary(
        self,
        name: Optional[str] = None,
        *,
        request_model: Optional[Type[BaseModel]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        description: str = "",
    ):
        def decorator(endpoint: Callable) -> Callable:
            self.service.add_method(
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
        def decorator(endpoint: Callable) -> Callable:
            self.service.add_method(
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
        def decorator(endpoint: Callable) -> Callable:
            self.service.add_method(
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
        def decorator(endpoint: Callable) -> Callable:
            self.service.add_method(
                name=name,
                endpoint=endpoint,
                method_class=StreamStreamMethod,
                request_model=request_model,
                response_model=response_model,
                description=description,
            )
            return endpoint

        return decorator

    def run(
        self,
        host: str = "127.0.0.1",
        port: int = 50051,
        server: Optional[Server] = None,
        reflection_enable: bool = True,
    ) -> None:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            self.run_async(
                host=host,
                port=port,
                server=server,
                reflection_enable=reflection_enable,
            )
        )
        loop.close()

    async def run_async(
        self,
        host: str = "127.0.0.1",
        port: int = 50051,
        server: Optional[Server] = None,
        reflection_enable: bool = True,
    ) -> None:
        server = grpc.aio.server() if not server else server
        server.add_insecure_port(f"{host}:{port}")
        self.add_to_server(server)
        if reflection_enable:
            self.enable_server_reflection(server)
        await server.start()
        logger.info(f"Running grpc on {host}:{port}")
        await server.wait_for_termination()

    def add_service(self, service: BaseService) -> None:
        if isinstance(service, Service):
            if not service.proto:
                service.proto = self.service.proto
        if service.full_name not in self._services:
            self._services[service.full_name] = service.copy()
        self._services[service.full_name].methods.update(service.methods)

    def add_to_server(self, server: Server):
        self.setup()
        for service in self._services.values():
            service.add_to_server(
                server, self._middlewares, self._server_streaming_middlewares
            )

    def enable_server_reflection(self, server: Server):
        service_names = [
            service.get_pb_full_name()
            for service in self._services.values()
            if service.grpc_servicer
        ]
        service_names.append(reflection.SERVICE_NAME)
        reflection.enable_server_reflection(service_names, server)
