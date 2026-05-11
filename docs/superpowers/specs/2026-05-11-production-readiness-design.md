# Production Readiness Design

## Overview

Add four production-grade features to FastGRPC: TLS/mTLS, graceful shutdown, health checking, and timeout/deadline control. Each feature is independent and opt-in, following the existing FastAPI-style philosophy.

## Feature 1: TLS/mTLS

### Scope
- `app.py`: `run()` and `run_async()` methods

### New Parameters on `run()` / `run_async()`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ssl_certificate_chain` | `str \| Path \| None` | `None` | Server certificate chain file path (PEM) |
| `ssl_private_key` | `str \| Path \| None` | `None` | Server private key file path (PEM) |
| `ca_certificate` | `str \| Path \| None` | `None` | CA root certificate path; providing it enables mTLS |

### Logic

- If both `ssl_certificate_chain` and `ssl_private_key` are provided: read files, call `grpc.ssl_server_credentials()` to build server credentials, use `server.add_secure_port()` instead of `add_insecure_port()`.
- If `ca_certificate` is also provided: pass `root_certificates` to enable mTLS (clients must present certificates signed by this CA).
- If neither is provided: keep existing behavior (`add_insecure_port`).

### API Example

```python
# TLS only
app.run(ssl_certificate_chain="server.crt", ssl_private_key="server.key")

# mTLS
app.run(
    ssl_certificate_chain="server.crt",
    ssl_private_key="server.key",
    ca_certificate="ca.crt",
)
```

### Dependencies
None — `grpc.ssl_server_credentials` is already part of `grpcio`.

---

## Feature 2: Graceful Shutdown

### Scope
- `app.py`: `run_async()` method

### New Parameter

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `graceful_timeout` | `float \| None` | `None` | Max seconds to wait for in-flight requests to complete after receiving a termination signal. `None` means immediate shutdown. |

### Logic

1. Register `SIGTERM` / `SIGINT` signal handlers in the asyncio event loop.
2. On signal: log "Shutting down gracefully...", call `server.stop(graceful_timeout)`.
3. `server.stop(None)` stops immediately (preserves backward compatibility).
4. `server.stop(30.0)` waits up to 30 seconds, then force-terminates.
5. Replace the blocking `server.wait_for_termination()` with an `asyncio.Event` that gets set when a signal is received.

### API Example

```python
# Production: wait up to 30s for in-flight requests
app.run(graceful_timeout=30.0)

# Dev/test: immediate shutdown (default)
app.run()
```

### Dependencies
None — pure `asyncio` + `grpc.aio` capabilities.

---

## Feature 3: Health Checking

### Scope
- `app.py`: `run()` / `run_async()` and `add_to_server()`

### New Parameter

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `health_check` | `bool` | `False` | Enable the gRPC Health Checking protocol (grpc.health.v1.Health) |

### Logic

1. When enabled, register the `grpc_health.v1.Health` servicer on the gRPC server.
2. Servicer reports `SERVING` / `NOT_SERVING` status for each registered service.
3. Natively compatible with K8s gRPC liveness/readiness probes.

### API Example

```python
app.run(health_check=True)
```

### Dependencies
`grpcio-health-checking>=1.43.0` — lazy-imported, only required when `health_check=True`.

---

## Feature 4: Timeout and Deadline Control

### Scope
- `app.py`: `FastGRPC.__init__()` and decorator methods
- `service.py`: `BaseMethod.__init__()` and `BaseMethod.__call__()`
- `context.py`: `ServiceContext`

### Three-Layer Timeout Configuration

| Level | Location | Description |
|-------|----------|-------------|
| Method | `@app.unary_unary(timeout=5.0)` | Per-RPC timeout in seconds |
| Service | `Service(name="X", timeout=10.0)` | Default timeout for all methods in a service |
| Global | `FastGRPC(timeout=30.0)` | Application-level fallback default |

Priority: method > service > global.

### Logic

1. Decorators accept an optional `timeout: float` parameter, forwarded to `BaseMethod.__init__()`.
2. The timeout resolution (method → service → global) happens in `BaseMethod`.
3. Deadline checking strategies differ by RPC mode:

| RPC Mode | Check Strategy |
|----------|---------------|
| Unary-Unary | Check `time_remaining()` once before `await endpoint()`. If expired, `abort(DEADLINE_EXCEEDED)`. |
| Stream-Unary | Check once before iterating the request stream; also check before calling `endpoint()` after collecting all requests. |
| Unary-Stream | Check before **each `yield`** in the async generator. If expired mid-stream, `abort(DEADLINE_EXCEEDED)`. |
| Stream-Stream | Check before each `yield` AND before processing each incoming message. |

4. `ServiceContext.time_remaining()` is already exposed and usable by business logic for custom deadline checks.

### API Example

```python
# Global fallback
app = FastGRPC(timeout=30.0)

# Method-level override
@app.unary_unary(timeout=5.0)
async def quick_op(request: HelloRequest) -> HelloReply:
    ...

# Check remaining deadline in business logic
@app.unary_unary()
async def slow_op(request: HelloRequest, ctx: ServiceContext) -> HelloReply:
    remaining = ctx.time_remaining()
    if remaining < 1.0:
        raise TimeoutError("not enough time")
    ...
```

### Dependencies
None.

---

## Files Affected

| File | Changes |
|------|---------|
| `fast_grpc/app.py` | New params on `__init__`, `run()`, `run_async()`, decorators; signal handling; TLS setup; health check registration |
| `fast_grpc/service.py` | `timeout` field on `BaseMethod`, deadline check in `__call__` |
| `fast_grpc/context.py` | No changes needed (`time_remaining()` already exists) |

## Backward Compatibility

All new parameters have defaults that preserve existing behavior. No breaking changes.
