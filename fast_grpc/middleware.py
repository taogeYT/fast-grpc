import typing

import grpc
from logzero import logger

from fast_grpc.context import ServiceContext
from fast_grpc.utils import message_to_str
from google.protobuf.message import Message


class ServerErrorMiddleware:
    async def __call__(
        self,
        call_next,
        request: typing.Union[Message, typing.AsyncIterable[Message]],
        context: ServiceContext,
    ):
        try:
            return await call_next(request, context)
        except Exception as e:
            logger.exception(
                f"GRPC invoke {context.service_method.name}({message_to_str(request)}) [Err] -> {repr(e)}"
            )
            await context.abort(grpc.StatusCode.INTERNAL, str(e))


class ServerStreamingErrorMiddleware:
    async def __call__(
        self,
        call_next,
        request: typing.Union[Message, typing.AsyncIterable[Message]],
        context: ServiceContext,
    ) -> typing.AsyncGenerator[Message, None]:
        try:
            async for response in call_next(request, context):
                yield response
        except Exception as e:
            logger.exception(
                f"GRPC invoke {context.service_method.name}({message_to_str(request)}) [Err] -> {repr(e)}"
            )
            await context.abort(grpc.StatusCode.INTERNAL, str(e))
