from unittest.mock import Mock

import grpc
import pytest
from pydantic import BaseModel

from fast_grpc.context import ServiceContext
from fast_grpc.middleware import ServerErrorMiddleware, ServerStreamingErrorMiddleware


class RequestModel(BaseModel):
    message: str


class ResponseModel(BaseModel):
    reply: str


@pytest.fixture
def mock_grpc_context():
    context = Mock(spec=grpc.ServicerContext)
    context.invocation_metadata.return_value = []
    context.is_active.return_value = True
    context.time_remaining.return_value = 30.0
    context.peer.return_value = "test_peer"
    return context


@pytest.fixture
def mock_service_context(mock_grpc_context):
    method_descriptor = Mock()
    method_descriptor.input_type._concrete_class = Mock()
    method_descriptor.output_type._concrete_class = Mock()

    # Create a mock method with name attribute
    mock_method = Mock()
    mock_method.name = "test_method"

    context = ServiceContext(
        grpc_context=mock_grpc_context,
        method=mock_method,
        method_descriptor=method_descriptor,
    )

    # Replace context methods with mocks for testing
    context.set_code = Mock()
    context.set_details = Mock()

    return context


@pytest.fixture
def server_error_middleware():
    return ServerErrorMiddleware()


@pytest.fixture
def server_streaming_error_middleware():
    return ServerStreamingErrorMiddleware()


async def test_server_error_middleware_success(
    server_error_middleware, mock_service_context
):
    mock_request = Mock()

    async def mock_call_next(request, context):
        return "success_response"

    result = await server_error_middleware(
        mock_call_next, mock_request, mock_service_context
    )
    assert result == "success_response"


async def test_server_error_middleware_exception(
    server_error_middleware, mock_service_context
):
    # Create a simple protobuf-like mock
    mock_request = Mock()
    mock_request.ListFields.return_value = []

    async def mock_call_next(request, context):
        raise ValueError("Test error")

    with pytest.raises(ValueError):
        await server_error_middleware(
            mock_call_next, mock_request, mock_service_context
        )

    # Verify error handling was called
    mock_service_context.set_code.assert_called_with(grpc.StatusCode.INTERNAL)
    mock_service_context.set_details.assert_called_with("Test error")


async def test_server_error_middleware_grpc_exception(
    server_error_middleware, mock_service_context
):
    mock_request = Mock()
    mock_request.ListFields.return_value = []

    async def mock_call_next(request, context):
        raise grpc.RpcError("gRPC error")

    with pytest.raises(grpc.RpcError):
        await server_error_middleware(
            mock_call_next, mock_request, mock_service_context
        )

    # Middleware should still set code/details for gRPC errors
    mock_service_context.set_code.assert_called_with(grpc.StatusCode.INTERNAL)
    mock_service_context.set_details.assert_called_with("gRPC error")


async def test_server_streaming_error_middleware_success(
    server_streaming_error_middleware, mock_service_context
):
    mock_request = Mock()
    mock_request.ListFields.return_value = []

    async def mock_call_next(request, context):
        yield "response_1"
        yield "response_2"

    responses = []
    async for response in server_streaming_error_middleware(
        mock_call_next, mock_request, mock_service_context
    ):
        responses.append(response)

    assert responses == ["response_1", "response_2"]


async def test_server_streaming_error_middleware_exception(
    server_streaming_error_middleware, mock_service_context
):
    mock_request = Mock()
    mock_request.ListFields.return_value = []

    async def mock_call_next(request, context):
        yield "response_1"
        raise ValueError("Test streaming error")

    with pytest.raises(ValueError):
        async for response in server_streaming_error_middleware(
            mock_call_next, mock_request, mock_service_context
        ):
            pass

    # Verify error handling was called
    mock_service_context.set_code.assert_called_with(grpc.StatusCode.INTERNAL)
    mock_service_context.set_details.assert_called_with("Test streaming error")


async def test_server_streaming_error_middleware_grpc_exception(
    server_streaming_error_middleware, mock_service_context
):
    mock_request = Mock()
    mock_request.ListFields.return_value = []

    async def mock_call_next(request, context):
        yield "response_1"
        raise grpc.RpcError("gRPC streaming error")

    with pytest.raises(grpc.RpcError):
        async for response in server_streaming_error_middleware(
            mock_call_next, mock_request, mock_service_context
        ):
            pass

    # Middleware should still set code/details for gRPC errors
    mock_service_context.set_code.assert_called_with(grpc.StatusCode.INTERNAL)
    mock_service_context.set_details.assert_called_with("gRPC streaming error")


async def test_custom_middleware_success():
    async def custom_middleware(call_next, request, context):
        # Pre-processing
        context.custom_data = "processed"
        response = await call_next(request, context)
        # Post-processing
        return f"wrapped_{response}"

    mock_request = Mock()
    mock_context = Mock()

    async def mock_call_next(request, context):
        return "original_response"

    result = await custom_middleware(mock_call_next, mock_request, mock_context)
    assert result == "wrapped_original_response"


async def test_custom_streaming_middleware_success():
    async def custom_streaming_middleware(call_next, request, context):
        # Pre-processing
        context.custom_data = "processed"

        async for response in call_next(request, context):
            # Process each response
            yield f"wrapped_{response}"

    mock_request = Mock()
    mock_context = Mock()

    async def mock_call_next(request, context):
        yield "response_1"
        yield "response_2"

    responses = []
    async for response in custom_streaming_middleware(
        mock_call_next, mock_request, mock_context
    ):
        responses.append(response)

    assert responses == ["wrapped_response_1", "wrapped_response_2"]
