# -*- coding: utf-8 -*-
import asyncio
import time
from typing import Callable, Optional

import grpc
from google.protobuf.text_format import MessageToString
from grpc import ServicerContext
from logzero import logger

from fast_grpc.types import App, Message
from fast_grpc.utils import await_sync_function


class BaseRPCMiddleware:
    def __init__(self, app: App, handler: Optional[Callable] = None):
        self.app = app
        self.handler = handler

    async def __call__(self, request: Message, context: ServicerContext, method):
        try:
            start_time = time.time()
            response = await self.app(request, context, method)
            message = MessageToString(request, as_one_line=True)
            end_time = time.time()
            elapsed_time = end_time - start_time
            logger.info(
                f"GRPC invoke {method.service.service_name}.{method.name}({message}) [OK] {elapsed_time:.3f} seconds"
            )
            return response
        except Exception as exc:
            if self.handler:
                if asyncio.iscoroutinefunction(self.handler):
                    response = await self.handler(request, context, exc)
                else:
                    response = await await_sync_function(self.handler)(request, context, exc)
                return response
            else:
                message = MessageToString(request, as_one_line=True)
                logger.exception(
                    f"GRPC invoke {method.service.service_name}.{method.name}({message}) [Err] -> {repr(exc)}"
                )
                await context.abort(grpc.StatusCode.UNKNOWN, repr(exc))
