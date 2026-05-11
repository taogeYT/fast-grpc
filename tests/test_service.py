import pytest
from pydantic import BaseModel
from fast_grpc.service import Service, MethodMode, BaseService
from typing import AsyncIterator


# Test models
class RequestModel(BaseModel):
    message: str


class ResponseModel(BaseModel):
    reply: str


# Test fixtures
@pytest.fixture
def service():
    return Service("TestService", "test.proto")


# Test cases
async def test_service_creation(service):
    assert isinstance(service, BaseService)
    assert service.name == "TestService"
    assert service.proto == "test.proto"
    assert service.methods == {}


async def test_unary_unary_method(service):
    @service.unary_unary()
    async def test_method(request: RequestModel) -> ResponseModel:
        return ResponseModel(reply=f"Received: {request.message}")

    assert "TestMethod" in service.methods
    method = service.methods["TestMethod"]
    assert method.mode == MethodMode.UNARY_UNARY
    assert method.request_model == RequestModel
    assert method.response_model == ResponseModel


async def test_unary_stream_method(service):
    @service.unary_stream()
    async def test_stream(request: RequestModel) -> AsyncIterator[ResponseModel]:
        for i in range(3):
            yield ResponseModel(reply=f"Stream {i}: {request.message}")

    assert "TestStream" in service.methods
    method = service.methods["TestStream"]
    assert method.mode == MethodMode.UNARY_STREAM
    assert method.request_model == RequestModel
    assert method.response_model == ResponseModel


async def test_stream_unary_method(service):
    @service.stream_unary()
    async def test_stream_unary(requests: AsyncIterator[RequestModel]) -> ResponseModel:
        messages = []
        async for request in requests:
            messages.append(request.message)
        return ResponseModel(reply=f"Received: {', '.join(messages)}")

    assert "TestStreamUnary" in service.methods
    method = service.methods["TestStreamUnary"]
    assert method.mode == MethodMode.STREAM_UNARY
    assert method.request_model == RequestModel
    assert method.response_model == ResponseModel


async def test_stream_stream_method(service):
    @service.stream_stream()
    async def test_stream_stream(
        requests: AsyncIterator[RequestModel],
    ) -> AsyncIterator[ResponseModel]:
        async for request in requests:
            yield ResponseModel(reply=f"Echo: {request.message}")

    assert "TestStreamStream" in service.methods
    method = service.methods["TestStreamStream"]
    assert method.mode == MethodMode.STREAM_STREAM
    assert method.request_model == RequestModel
    assert method.response_model == ResponseModel


async def test_invalid_request_model_raises_value_error(service):
    class NotAModel:
        pass

    with pytest.raises(ValueError, match="request_model must be a BaseModel subclass"):

        @service.unary_unary(request_model=NotAModel)
        async def test_method(request: RequestModel) -> ResponseModel:
            return ResponseModel(reply=f"Received: {request.message}")


async def test_invalid_response_model_raises_value_error(service):
    class NotAModel:
        pass

    with pytest.raises(ValueError, match="response_model must be a BaseModel subclass"):

        @service.unary_unary(response_model=NotAModel)
        async def test_method(request: RequestModel) -> ResponseModel:
            return ResponseModel(reply=f"Received: {request.message}")


async def test_serialize_response_with_from_attributes():
    """verify serialize_response uses from_attributes=True to accept objects with attributes"""
    from unittest.mock import Mock, patch
    from fast_grpc.service import UnaryUnaryMethod

    async def endpoint(request: RequestModel) -> ResponseModel:
        return ResponseModel(reply="ok")

    method = UnaryUnaryMethod(
        endpoint=endpoint,
        request_model=RequestModel,
        response_model=ResponseModel,
    )

    mock_context = Mock()

    class DummyPBType:
        pass

    mock_context.output_type = DummyPBType

    class ArbitraryResponse:
        reply = "hello from attribute"

    with patch("fast_grpc.service.pydantic_to_message") as mock_convert:
        method.serialize_response(ArbitraryResponse(), mock_context)
        # If we reach here without ValidationError, from_attributes=True worked
        mock_convert.assert_called_once()
        validated = mock_convert.call_args[0][0]
        assert isinstance(validated, ResponseModel)
        assert validated.reply == "hello from attribute"


async def test_method_stores_timeout():
    """BaseMethod stores the timeout parameter."""
    from fast_grpc.service import UnaryUnaryMethod

    async def endpoint(request: RequestModel) -> ResponseModel:
        return ResponseModel(reply="ok")

    method = UnaryUnaryMethod(
        endpoint=endpoint,
        request_model=RequestModel,
        response_model=ResponseModel,
        timeout=5.0,
    )
    assert method.timeout == 5.0


async def test_method_timeout_defaults_to_none():
    """BaseMethod timeout defaults to None when not specified."""
    from fast_grpc.service import UnaryUnaryMethod

    async def endpoint(request: RequestModel) -> ResponseModel:
        return ResponseModel(reply="ok")

    method = UnaryUnaryMethod(
        endpoint=endpoint,
        request_model=RequestModel,
        response_model=ResponseModel,
    )
    assert method.timeout is None


async def test_service_stores_timeout():
    """Service stores timeout parameter."""
    srv = Service("TestService", "test.proto", timeout=10.0)
    assert srv.timeout == 10.0


async def test_service_timeout_defaults_to_none():
    """Service timeout defaults to None."""
    srv = Service("TestService", "test.proto")
    assert srv.timeout is None


async def test_unary_timeout_aborts_when_exceeded():
    """Unary method aborts with DEADLINE_EXCEEDED when server timeout is exceeded."""
    from fast_grpc.service import UnaryUnaryMethod
    from unittest.mock import AsyncMock, Mock, patch
    import grpc

    async def endpoint(request: RequestModel) -> ResponseModel:
        return ResponseModel(reply="ok")

    method = UnaryUnaryMethod(
        endpoint=endpoint,
        request_model=RequestModel,
        response_model=ResponseModel,
        timeout=5.0,
    )

    mock_context = Mock()
    mock_abort = AsyncMock()
    mock_context.abort = mock_abort
    mock_context.elapsed_time = 5100  # 5.1 seconds in ms

    with patch.object(method, "serialize_response", return_value=Mock()):
        with patch("fast_grpc.service.message_to_pydantic") as mock_convert:
            with patch("fast_grpc.service.message_to_str", return_value=""):
                mock_context.service_method = Mock()
                mock_context.service_method.name = "TestMethod"
                mock_convert.return_value = RequestModel(message="hello")
                await method(Mock(), mock_context)

    mock_abort.assert_called_once_with(
        grpc.StatusCode.DEADLINE_EXCEEDED, "Server timeout: 5.0s"
    )


async def test_unary_timeout_proceeds_when_not_exceeded():
    """Unary method proceeds normally when timeout is not exceeded."""
    from fast_grpc.service import UnaryUnaryMethod
    from unittest.mock import AsyncMock, Mock, patch

    async def endpoint(request: RequestModel) -> ResponseModel:
        return ResponseModel(reply="ok")

    method = UnaryUnaryMethod(
        endpoint=endpoint,
        request_model=RequestModel,
        response_model=ResponseModel,
        timeout=5.0,
    )

    mock_context = Mock()
    mock_context.abort = AsyncMock()
    mock_context.elapsed_time = 1000  # 1 second in ms
    mock_context.service_method = Mock()
    mock_context.service_method.name = "TestMethod"

    with patch.object(method, "serialize_response", return_value=Mock()):
        with patch("fast_grpc.service.message_to_pydantic") as mock_convert:
            with patch("fast_grpc.service.message_to_str") as mock_msg_str:
                mock_convert.return_value = RequestModel(message="hello")
                mock_msg_str.return_value = "request"
                result = await method(Mock(), mock_context)

    mock_context.abort.assert_not_called()
    assert result is not None


async def test_unary_stream_timeout_aborts_mid_stream():
    """Unary-Stream aborts when timeout exceeded during streaming."""
    from fast_grpc.service import UnaryStreamMethod
    from unittest.mock import AsyncMock, Mock, patch
    import grpc

    async def endpoint(request: RequestModel):
        yield ResponseModel(reply="item1")
        yield ResponseModel(reply="item2")

    method = UnaryStreamMethod(
        endpoint=endpoint,
        request_model=RequestModel,
        response_model=ResponseModel,
        timeout=1.0,
    )

    mock_context = Mock()
    mock_abort = AsyncMock()
    mock_context.abort = mock_abort
    mock_context.elapsed_time = 500  # 0.5s in ms (under 1.0s)

    with patch.object(method, "serialize_response", return_value=Mock()):
        with patch("fast_grpc.service.message_to_pydantic") as mock_convert:
            mock_convert.return_value = RequestModel(message="hello")

            gen = method(Mock(), mock_context)
            # First yield succeeds (elapsed=500ms < 1000ms)
            await gen.__anext__()
            mock_abort.assert_not_called()

            # Simulate time passing past timeout
            mock_context.elapsed_time = 1500  # 1.5s in ms (> 1.0s)
            # After abort, loop iterates to next yield from endpoint
            items = []
            with patch("fast_grpc.service.message_to_str", return_value=""):
                mock_context.service_method = Mock()
                mock_context.service_method.name = "TestMethod"
                async for item in gen:
                    items.append(item)
            assert len(items) == 1  # Only second endpoint yield, after timeout

    mock_abort.assert_called_once_with(
        grpc.StatusCode.DEADLINE_EXCEEDED, "Server timeout: 1.0s"
    )
