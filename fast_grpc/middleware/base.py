# -*- coding: utf-8 -*-
import time
from typing import Callable, Optional

import grpc
from google.protobuf.message import Message
from google.protobuf.text_format import MessageToString
from logzero import logger

from fast_grpc.types import Method, ServiceContext


class BaseGRPCMiddleware:
    def __init__(self, dispatch: Optional[Callable] = None):
        self.dispatch_func = dispatch

    async def __call__(self, method: Method, request: Message, context: ServiceContext):
        try:
            start_time = time.time()
            response = await method(request, context)
            message = MessageToString(request, as_one_line=True)
            end_time = time.time()
            elapsed_time = end_time - start_time
            logger.info(
                f"GRPC invoke {context.service_method.name}({message}) [OK] {elapsed_time:.3f} seconds"
            )
            return response
        except Exception as exc:
            if self.dispatch_func:
                response = await self.dispatch_func(request, context, exc)
                return response
            else:
                message = MessageToString(request, as_one_line=True)
                logger.exception(
                    f"GRPC invoke {context.service_method.__name__}({message}) [Err] -> {repr(exc)}"
                )
                await context.abort(grpc.StatusCode.UNKNOWN, repr(exc))
