# -*- coding: utf-8 -*-
import asyncio
import inspect
from typing import Any, Callable, List, Optional, Sequence, Type

import grpc
from grpc.aio._typing import ChannelArgumentType  # noqa
from logzero import logger
from pydantic import BaseModel

from fast_grpc.middleware import Middleware
from fast_grpc.middleware.base import BaseRPCMiddleware
from fast_grpc.service import Service


class FastGRPC(object):
    def __init__(
        self,
        default_service_name: Optional[str] = None,
        middleware: Optional[Sequence[Middleware]] = None,
    ):
        self.services = []
        if default_service_name:
            self.default_service = Service(type(default_service_name, (object,), {}))
            self.services.append(self.default_service)
        else:
            self.default_service = None
        self.rpc_startup_funcs: List[Callable[..., Any]] = []
        self.rpc_shutdown_funcs: List[Callable[..., Any]] = []
        self.user_middleware: List[Middleware] = [] if middleware is None else list(middleware)

    def setup(self) -> None:
        # build proto
        for service in self.services:
            service.gen_and_compile_proto()

    def on_startup(self, func: Callable[..., None]):
        self.rpc_startup_funcs.append(func)

    def add_middleware(self, middleware_class: type, **options: Any) -> None:
        self.user_middleware.insert(0, Middleware(middleware_class, **options))

    def run(
        self,
        host: str = "127.0.0.1",
        port: int = 50051,
        options: Optional[ChannelArgumentType] = None,
        maximum_concurrent_rpcs: Optional[int] = None,
        compression: Optional[grpc.Compression] = None,
    ) -> None:
        # asyncio.run(self.run_async(host=host, port=port))
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
        def build_middleware_stack(app):
            middleware = [Middleware(BaseRPCMiddleware)]
            for cls, options in middleware:
                app = cls(app=app, **options)
            return app

        self.setup()
        for handler in self.rpc_startup_funcs:
            if inspect.iscoroutinefunction(handler):
                await handler()
            else:
                handler()
        server = grpc.aio.server(
            options=options,
            maximum_concurrent_rpcs=maximum_concurrent_rpcs,
            compression=compression,
        )
        for service in self.services:
            service.bind_server(server, build_middleware_stack(service))
        logger.info(f"Running grpc on {host}:{port}")
        server.add_insecure_port(f"{host}:{port}")
        await server.start()
        await server.wait_for_termination()

    def add_method(self, name, *, request_model: Type[BaseModel], response_model: Type[BaseModel]) -> Callable:
        def decorator(func: Callable) -> Callable:
            if self.default_service is None:
                raise ValueError("Need set default_service_name")
            self.default_service.add_rpc_method(name, func, request_model=request_model, response_model=response_model)
            return func

        return decorator

    def add_service(self, servicer):
        self.services.append(Service(servicer))
