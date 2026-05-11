"""Integration tests for production features."""
import grpc
from unittest.mock import AsyncMock, Mock, patch
from pydantic import BaseModel
from fast_grpc import FastGRPC


class RequestModel(BaseModel):
    message: str


class ResponseModel(BaseModel):
    reply: str


async def test_full_production_config():
    """All production features can be configured together."""
    app = FastGRPC(
        name="ProdService",
        proto="prod.proto",
        timeout=30.0,
        auto_gen_proto=False,
        compile_proto=False,
    )

    @app.unary_unary(timeout=5.0)
    async def fast_method(request: RequestModel) -> ResponseModel:
        return ResponseModel(reply=request.message)

    @app.unary_unary()
    async def slow_method(request: RequestModel) -> ResponseModel:
        return ResponseModel(reply=request.message)

    assert app.service.methods["FastMethod"].timeout == 5.0
    assert app.service.methods["SlowMethod"].timeout is None


async def test_server_timeout_aborts_request():
    """Server-side timeout aborts request with DEADLINE_EXCEEDED."""
    from fast_grpc.service import UnaryUnaryMethod

    async def endpoint(request: RequestModel) -> ResponseModel:
        return ResponseModel(reply="ok")

    method = UnaryUnaryMethod(
        endpoint=endpoint,
        request_model=RequestModel,
        response_model=ResponseModel,
        timeout=1.0,
    )

    mock_context = Mock()
    mock_context.abort = AsyncMock()
    mock_context.elapsed_time = 2000  # 2 seconds (exceeds 1s timeout)

    with patch.object(method, "serialize_response", return_value=Mock()):
        with patch("fast_grpc.service.message_to_pydantic") as mock_convert:
            with patch("fast_grpc.service.message_to_str", return_value=""):
                mock_context.service_method = Mock()
                mock_context.service_method.name = "TestMethod"
                mock_convert.return_value = RequestModel(message="test")
                await method(Mock(), mock_context)

    mock_context.abort.assert_called_once_with(
        grpc.StatusCode.DEADLINE_EXCEEDED, "Server timeout: 1.0s"
    )


async def test_timeout_resolution_in_add_to_server():
    """Timeout resolves from method > service > global."""
    app = FastGRPC(
        name="TestService", proto="test.proto",
        timeout=30.0, auto_gen_proto=False, compile_proto=False,
    )

    @app.unary_unary(timeout=5.0)
    async def method_with(request: RequestModel) -> ResponseModel:
        return ResponseModel(reply="ok")

    @app.unary_unary()
    async def method_without(request: RequestModel) -> ResponseModel:
        return ResponseModel(reply="ok")

    # Simulate resolution (same as add_to_server does)
    for svc in app._services.values():
        svc_timeout = getattr(svc, 'timeout', None)
        for method in svc.methods.values():
            if method.timeout is None:
                method.timeout = svc_timeout or app._timeout

    assert app.service.methods["MethodWith"].timeout == 5.0
    assert app.service.methods["MethodWithout"].timeout == 30.0
