# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Callable, Any, Union, AsyncIterator

from google.protobuf.message import Message

from fast_grpc.context import ServiceContext
from fast_grpc.types import Method


class BaseMiddleware:
    async def __call__(
        self,
        method: Method,
        request: Union[Message, AsyncIterator[Message]],
        context: ServiceContext,
    ) -> Any:
        return method(request, context)


class MiddlewareManager:
    def __init__(self, middlewares: List[BaseMiddleware]):
        self._middleware: List[BaseMiddleware] = middlewares

    def add_middleware(self, middleware: BaseMiddleware):
        """添加中间件"""
        self._middleware.append(middleware)

    async def dispatch(
        self,
        handler: Callable,
        request: Any,
        context: ServiceContext,
    ) -> Any:
        async def execute_middleware(index: int) -> Any:
            if index >= len(self._middleware):
                return await handler(request, context)

            middleware = self._middleware[index]
            return await middleware(
                lambda req, ctx: execute_middleware(index + 1), request, context
            )

        return await execute_middleware(0)
