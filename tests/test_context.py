import time
from unittest.mock import Mock

import grpc
import pytest

from fast_grpc.context import ServiceContext


@pytest.fixture
def mock_grpc_context():
    context = Mock(spec=grpc.ServicerContext)
    context.invocation_metadata.return_value = [("key1", "value1"), ("key2", "value2")]
    context.is_active.return_value = True
    context.time_remaining.return_value = 30.0
    context.peer.return_value = "test_peer"
    return context


@pytest.fixture
def service_context(mock_grpc_context):
    method_descriptor = Mock()
    method_descriptor.input_type._concrete_class = Mock()
    method_descriptor.output_type._concrete_class = Mock()

    return ServiceContext(
        grpc_context=mock_grpc_context,
        method=Mock(),
        method_descriptor=method_descriptor,
    )


async def test_service_context_initialization(service_context, mock_grpc_context):
    assert service_context.grpc_context == mock_grpc_context
    assert service_context.input_type is not None
    assert service_context.output_type is not None
    assert service_context._start_time > 0


async def test_elapsed_time_property(service_context):
    # Test that elapsed_time returns milliseconds
    time.sleep(0.1)  # Sleep for 100ms
    elapsed = service_context.elapsed_time
    assert elapsed >= 100  # Should be at least 100ms
    assert elapsed < 200  # Should be less than 200ms


async def test_metadata_property(service_context):
    metadata = service_context.metadata
    assert metadata == {"key1": "value1", "key2": "value2"}

    # Test caching - second call should return same result
    metadata2 = service_context.metadata
    assert metadata2 == metadata


async def test_is_active_property(service_context, mock_grpc_context):
    result = service_context.is_active()
    assert result is True
    mock_grpc_context.is_active.assert_called_once()


async def test_time_remaining_property(service_context, mock_grpc_context):
    result = service_context.time_remaining()
    assert result == 30.0
    mock_grpc_context.time_remaining.assert_called_once()


async def test_peer_property(service_context, mock_grpc_context):
    result = service_context.peer()
    assert result == "test_peer"
    mock_grpc_context.peer.assert_called_once()


async def test_invocation_metadata_property(service_context, mock_grpc_context):
    result = service_context.invocation_metadata()
    assert result == [("key1", "value1"), ("key2", "value2")]
    mock_grpc_context.invocation_metadata.assert_called_once()


async def test_set_code_method(service_context, mock_grpc_context):
    service_context.set_code(grpc.StatusCode.NOT_FOUND)
    mock_grpc_context.set_code.assert_called_with(grpc.StatusCode.NOT_FOUND)


async def test_set_details_method(service_context, mock_grpc_context):
    service_context.set_details("Resource not found")
    mock_grpc_context.set_details.assert_called_with("Resource not found")


async def test_abort_method(service_context, mock_grpc_context):
    service_context.abort(grpc.StatusCode.NOT_FOUND, "Resource not found")
    mock_grpc_context.abort.assert_called_with(
        grpc.StatusCode.NOT_FOUND, "Resource not found"
    )


async def test_abort_with_status_method(service_context, mock_grpc_context):
    mock_status = Mock()
    service_context.abort_with_status(mock_status)
    mock_grpc_context.abort_with_status.assert_called_with(mock_status)


async def test_metadata_caching(service_context, mock_grpc_context):
    # First call should populate cache
    metadata1 = service_context.metadata

    # Second call should use cache, not call invocation_metadata again
    metadata2 = service_context.metadata

    assert metadata1 == metadata2
    mock_grpc_context.invocation_metadata.assert_called_once()


async def test_elapsed_time_accuracy():
    # Test that elapsed_time calculates correctly
    mock_grpc_context = Mock()
    method_descriptor = Mock()
    method_descriptor.input_type._concrete_class = Mock()
    method_descriptor.output_type._concrete_class = Mock()

    context = ServiceContext(
        grpc_context=mock_grpc_context,
        method=Mock(),
        method_descriptor=method_descriptor,
    )

    # Get initial elapsed time (should be very small)
    initial_elapsed = context.elapsed_time
    assert initial_elapsed >= 0
    assert initial_elapsed < 50  # Should be less than 50ms

    # Wait a bit and check again
    time.sleep(0.1)
    elapsed_after_sleep = context.elapsed_time
    assert elapsed_after_sleep >= 100  # Should be at least 100ms
    assert elapsed_after_sleep < 200  # Should be less than 200ms
