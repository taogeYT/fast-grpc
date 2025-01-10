# -*- coding: utf-8 -*-
import asyncio
from typing import Callable, Optional, Type

import grpc
from grpc.aio._typing import ChannelArgumentType  # noqa
from grpc.aio import Server
from logzero import logger
from pydantic import BaseModel

from fast_grpc.proto import render_proto_file, ProtoBuilder
from fast_grpc.service import (
    Service,
    UnaryUnaryMethod,
    UnaryStreamMethod,
    StreamUnaryMethod,
    StreamStreamMethod,
)
from fast_grpc.utils import protoc_compile


class FastGRPC(object):
    def __init__(
        self,
        *,
        service_name: str = "FastGRPC",
        proto: str = "fast_grpc.proto",
        auto_gen_proto: bool = True,
    ):
        self.service = Service(name=service_name, proto=proto)
        self._services: dict[str, Service] = {f"{proto}:{service_name}": self.service}
        self._auto_gen_proto = auto_gen_proto

    def setup(self) -> None:
        builders = {}
        for service in self._services.values():
            if service.proto_path not in builders:
                builders[service.proto_path] = ProtoBuilder(
                    package=service.proto_path.stem
                )
            builders[service.proto_path].add_service(service)
        for proto, builder in builders.items():
            if self._auto_gen_proto:
                proto_define = builder.get_proto()
                content = render_proto_file(proto_define)
                proto.parent.mkdir(parents=True, exist_ok=True)
                proto.write_text(content)
                logger.info(f"Created {proto} file success")
            protoc_compile(proto)

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
    ) -> None:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            self.run_async(
                host=host,
                port=port,
                server=server,
            )
        )
        loop.close()

    async def run_async(
        self,
        host: str = "127.0.0.1",
        port: int = 50051,
        server: Optional[Server] = None,
    ) -> None:
        self.setup()
        server = grpc.aio.server() if not server else server
        for service in self._services.values():
            service.add_to_server(server)
        server.add_insecure_port(f"{host}:{port}")
        await server.start()
        logger.info(f"Running grpc on {host}:{port}")
        await server.wait_for_termination()

    def add_service(self, service: Service):
        if not service.proto:
            service.proto = self.service.proto
        path_name = f"{service.proto}:{service.name}"
        if path_name not in self._services:
            self._services[path_name] = Service(name=service.name, proto=service.proto)
        self._services[path_name].methods.update(service.methods)
