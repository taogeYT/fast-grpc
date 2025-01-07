# -*- coding: utf-8 -*-
import asyncio
import collections
import os.path
from typing import Any, Callable, List, Optional, Type, TypeVar

import grpc
from grpc.aio._typing import ChannelArgumentType  # noqa
from logzero import logger
from pydantic import BaseModel

from fast_grpc.proto import render_proto_file, ProtoBuilder
from fast_grpc.service import Service, UnaryUnaryMethod, add_service_to_server
from fast_grpc.utils import protoc_compile

T = TypeVar('T')
R = TypeVar('R')


class FastGRPC(object):
    def __init__(self, name: str = "FastGRPC", proto: str="fast_grpc.proto"):
        self.proto = proto
        self.rpc_startup_funcs: List[Callable[..., Any]] = []
        self.rpc_shutdown_funcs: List[Callable[..., Any]] = []
        self.service = Service(name=name, proto=proto)
        self._services: dict[str, Service] = {f"{proto}:{name}": self.service}

    def setup(self) -> None:
        builders = {}
        for service in self._services.values():
            if service.proto not in builders:
                builders[service.proto] = ProtoBuilder(proto_path=service.proto)
            builders[service.proto].add_service(service)
        for proto, builder in builders.items():
            proto_define = builder.get_proto()
            content = render_proto_file(proto_define)
            if not os.path.exists(proto):
                directory = os.path.dirname(proto)
                os.makedirs(directory, exist_ok=True)
                with open(proto, "w") as f:
                    f.write(content)
            else:
                logger.info(f"FastGRPC setup proto file {proto} [Skip] -> proto exists")
            protoc_compile(proto)

    def on_startup(self, func: Callable[..., None]):
        self.rpc_startup_funcs.append(func)

    def unary_unary(
        self,
        name: Optional[str] = None,
        *,
        request_model: Optional[Type[BaseModel]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        description: str = ""
    ):
        def decorator(endpoint: Callable[[T], R]) -> Callable[[T], R]:
            self.service.add_method(
                name=name,
                endpoint=endpoint,
                method_class=UnaryUnaryMethod,
                request_model=request_model,
                response_model=response_model,
                description=description
            )
            return endpoint

        return decorator

    def run(
        self,
        host: str = "127.0.0.1",
        port: int = 50051,
        options: Optional[ChannelArgumentType] = None,
        maximum_concurrent_rpcs: Optional[int] = None,
        compression: Optional[grpc.Compression] = None,
    ) -> None:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            self.run_async(
                host=host,
                port=port,
                options=options,
                maximum_concurrent_rpcs=maximum_concurrent_rpcs,
                compression=compression,
            )
        )
        loop.close()

    async def run_async(
        self,
        host: str = "127.0.0.1",
        port: int = 50051,
        options: Optional[ChannelArgumentType] = None,
        maximum_concurrent_rpcs: Optional[int] = None,
        compression: Optional[grpc.Compression] = None,
    ) -> None:
        self.setup()
        server = grpc.aio.server(
            options=options,
            maximum_concurrent_rpcs=maximum_concurrent_rpcs,
            compression=compression,
        )
        self._register_service_to_server(server)
        logger.info(f"Running grpc on {host}:{port}")
        server.add_insecure_port(f"{host}:{port}")
        await server.start()
        await server.wait_for_termination()

    def add_service(self, service: Service):
        if service.proto is None:
            service.proto = self.proto
        path_name = f"{service.proto}:{service.name}"
        if path_name not in self._services:
            self._services[path_name] = Service(name=service.name, proto=service.proto)
        self._services[path_name].methods.update(service.methods)

    def _register_service_to_server(self, server):
        for service in self._services.values():
            add_service_to_server(service, server)
