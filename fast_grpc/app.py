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
from fast_grpc.types import App


class FastGRPC(object):
    def __init__(
        self,
        default_service_name: str = "FastGRPC",
        middleware: Optional[Sequence[Middleware]] = None,
    ):
        self.default_service_name = default_service_name
        self.service = Service(service_name=self.default_service_name)

        self.rpc_startup_funcs: List[Callable[..., Any]] = []
        self.rpc_shutdown_funcs: List[Callable[..., Any]] = []
        self.user_middleware: List[Middleware] = [] if middleware is None else list(middleware)
        self.middleware_stack: App = self.build_middleware_stack()

    def setup(self) -> None:
        # build proto
        self.service.gen_and_compile_proto()

    def on_startup(self, func: Callable[..., None]):
        self.rpc_startup_funcs.append(func)

    def add_middleware(self, middleware_class: type, **options: Any) -> None:
        self.user_middleware.insert(0, Middleware(middleware_class, **options))
        self.middleware_stack = self.build_middleware_stack()

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
        self.service.bind_server(server, self)
        logger.info(f"Running grpc on {host}:{port}")
        server.add_insecure_port(f"{host}:{port}")
        await server.start()
        await server.wait_for_termination()

    def add_method(self, name, *, request_model: Type[BaseModel], response_model: Type[BaseModel]) -> Callable:
        def decorator(func: Callable) -> Callable:
            self.service.add_rpc_method(name, func, request_model=request_model, response_model=response_model)
            return func

        return decorator

    def build_middleware_stack(self):
        middleware = [Middleware(BaseRPCMiddleware)]
        app = self.service
        for cls, options in middleware:
            app = cls(app=app, **options)
        return app

    async def __call__(self, request, context, handler):
        return await self.middleware_stack(request, context, handler)
