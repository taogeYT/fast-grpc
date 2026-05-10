# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Setup
make install              # poetry install + pre-commit hooks

# Lint & format
make lint                 # ruff check + ruff format --check + mypy fast_grpc
make format               # ruff check --fix + ruff format

# Test (pytest-asyncio with asyncio_mode=auto — no @pytest.mark.asyncio needed)
poetry run pytest tests -v
poetry run pytest tests -v -k "test_name_pattern"

# Build
poetry build
```

## Architecture

FastGRPC is a decorator-driven gRPC framework for Python 3.9+ patterned after FastAPI. The core flow:

1. **Define** — Users decorate async functions with `@app.unary_unary()` (or `unary_stream`/`stream_unary`/`stream_stream`), providing Pydantic models as request/response types.
2. **Proto generation** — `ProtoBuilder` (in `proto.py`) introspects the Pydantic type annotations and Jinja2 templates to auto-generate `.proto` files.
3. **Compilation** — `protoc_compile()` shells out to `grpc_tools.protoc` to compile `.proto` → `*_pb2.py` / `*_pb2_grpc.py`.
4. **Dynamic servicer** — `make_grpc_service_from_methods()` (in `service.py`) dynamically creates gRPC servicer classes at runtime using `type()`, wrapping user endpoints with middleware and `ServiceContext`.
5. **Server** — `FastGRPC.run()` creates an `grpc.aio` server, registers all services, optionally enables reflection, and starts serving.

Key modules:

- **`app.py`** — `FastGRPC` class: the main entry point. Owns a default `Service` and a dict of named services. Decorators delegate to `self.service.add_method()`. `setup()` orchestrates proto generation + compilation. `add_to_server()` registers all services onto a gRPC server.
- **`service.py`** — `BaseService` (ABC), `Service` (proto-based), `Pb2Service` (precompiled pb2 modules), and `BaseMethod` subclasses for the 4 RPC modes. `make_grpc_service_from_methods()` is the runtime class factory that wires endpoints → servicer methods with middleware chaining.
- **`proto.py`** — `ProtoBuilder` (service method → proto schema → `.proto` file), `ClientBuilder` (compiled descriptor → Python Pydantic client), and `proto_to_python_client()` convenience function. Uses Jinja2 templates for both proto and Python client generation.
- **`context.py`** — `ServiceContext` wraps `grpc.ServicerContext` with `elapsed_time`, `metadata` dict, and delegation methods (`abort`, `set_code`, `peer`, etc.).
- **`middleware.py`** — `ServerErrorMiddleware` (unary) and `ServerStreamingErrorMiddleware` (streaming). Both catch exceptions, log them, set INTERNAL gRPC status code, and re-raise.
- **`types.py`** — `Empty` model, `ProtoTag` for custom type mapping, `PYTHON_TO_PROTOBUF_TYPES` lookup, and constrained type aliases (`Uint32`, `Int64`, `Double`, etc.).
- **`utils.py`** — Naming converters (`camel_to_snake`, `snake_to_camel`), dynamic proto module loader, `protoc_compile` subprocess runner, and protobuf ←→ Pydantic conversion helpers.

## Service keying

Services are keyed by `full_name`: `"{proto}:{name}"` for `Service`, `"{pb2_module.__name__}:{name}"` for `Pb2Service`. When the same full_name is added via `add_service()`, methods are merged into the existing service.

## Middleware signature

Unary middleware: `async def mw(call_next, request, context) -> response` — calls `await call_next(request, context)`.
Streaming middleware: `async def mw(call_next, request, context) -> response` — iterates `async for response in call_next(request, context)` and yields.

Built-in error middleware is always prepended to the middleware lists.

## Proto compilation

`protoc_compile()` compiles ALL `.proto` files in the same directory as the target proto file, not just the single file. It runs from the project root (`.`), so proto imports must be relative to that.

## CI

GitHub Actions on PRs/pushes to `main` runs the test matrix across Python 3.9/3.10/3.11 with multiple protobuf/grpcio version combinations. No other CI checks (linting is only via pre-commit hooks locally).
