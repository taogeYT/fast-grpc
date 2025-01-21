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
