# -*- coding: utf-8 -*-
import asyncio
import signal
from pathlib import Path
from typing import Callable, Optional, Type

import grpc
from grpc.aio import Server
from grpc.aio._typing import ChannelArgumentType  # noqa
from grpc_reflection.v1alpha import reflection
from logzero import logger
from pydantic import BaseModel

from fast_grpc.middleware import ServerErrorMiddleware, ServerStreamingErrorMiddleware
from fast_grpc.proto import ProtoBuilder
from fast_grpc.service import (
    BaseService,
    Service,
    StreamStreamMethod,
    StreamUnaryMethod,
    UnaryStreamMethod,
    UnaryUnaryMethod,
)
from fast_grpc.types import ProtoTag
from fast_grpc.utils import protoc_compile


class FastGRPC(object):
    """
    `FastGRPC` app class, the main entrypoint to use FastGRPC.

    ## Example

    ```python
    from fast_grpc import FastGRPC

    app = FastGRPC(name="Greeter", proto="greeter.proto")
    ```
    """

    def __init__(
        self,
        *,
        name: str = "FastGRPC",
        proto: str = "fast_grpc.proto",
        auto_gen_proto: bool = True,
        type_mapping: Optional[dict[type, ProtoTag]] = None,
        compile_proto: bool = True,
        generate_mypy: bool = False,
        timeout: Optional[float] = None,
    ):
        """
        Args:
            name: default grpc service name.
            proto: grpc proto file path.
            auto_gen_proto: Whether to automatically generate proto file or not. if not, the proto file will be defined by yourself.
            type_mapping: custom type mapping.
            compile_proto: Whether to compile proto file or not.
            generate_mypy: Whether to generate mypy stubs or not.
            timeout: default timeout in seconds for all methods (can be overridden per-service and per-method).
        """
        self.service = Service(name=name, proto=proto, timeout=timeout)
        self._services: dict[str, Service] = {f"{proto}:{name}": self.service}
        self._auto_gen_proto = auto_gen_proto
        self._middlewares: list[Callable] = [ServerErrorMiddleware()]
        self._server_streaming_middlewares: list[Callable] = [
            ServerStreamingErrorMiddleware()
        ]
        self._type_mapping = type_mapping
        self._compile_proto = compile_proto
        self._generate_mypy = generate_mypy
        self._timeout = timeout

    def setup(self) -> None:
        builders = {}
        for service in self._services.values():
            if not service.methods or not isinstance(service, Service):
                continue
            path = Path(service.proto)
            if path not in builders:
                builders[path] = ProtoBuilder(
                    package=path.stem, type_mapping=self._type_mapping
                )
            builders[path].add_service(service)
        for proto, builder in builders.items():
            if self._auto_gen_proto:
                proto_define = builder.get_proto()
                content = proto_define.render_proto_file()
                proto.parent.mkdir(parents=True, exist_ok=True)
                proto.write_text(content)
                logger.info(f"Created {proto} file success")
            if self._compile_proto:
                protoc_compile(proto, generate_mypy=self._generate_mypy)

    def add_middleware(self, middleware: Callable, is_server_streaming=False) -> None:
        if is_server_streaming:
            self._server_streaming_middlewares.append(middleware)
        else:
            self._middlewares.append(middleware)

    def middleware(self, is_server_streaming=False):
        def decorator(func: Callable) -> Callable:
            self.add_middleware(func, is_server_streaming)
            return func

        return decorator

    def unary_unary(
        self,
        name: Optional[str] = None,
        *,
        request_model: Optional[Type[BaseModel]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        description: str = "",
        timeout: Optional[float] = None,
    ):
        def decorator(endpoint: Callable) -> Callable:
            self.service.add_method(
                name=name,
                endpoint=endpoint,
                method_class=UnaryUnaryMethod,
                request_model=request_model,
                response_model=response_model,
                description=description,
                timeout=timeout,
            )
            return endpoint

        return decorator

    def unary_stream(
        self,
        name: Optional[str] = None,
        *,
        request_model: Optional[Type[BaseModel]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        description: str = "",
        timeout: Optional[float] = None,
    ):
        def decorator(endpoint: Callable) -> Callable:
            self.service.add_method(
                name=name,
                endpoint=endpoint,
                method_class=UnaryStreamMethod,
                request_model=request_model,
                response_model=response_model,
                description=description,
                timeout=timeout,
            )
            return endpoint

        return decorator

    def stream_unary(
        self,
        name: Optional[str] = None,
        *,
        request_model: Optional[Type[BaseModel]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        description: str = "",
        timeout: Optional[float] = None,
    ):
        def decorator(endpoint: Callable) -> Callable:
            self.service.add_method(
                name=name,
                endpoint=endpoint,
                method_class=StreamUnaryMethod,
                request_model=request_model,
                response_model=response_model,
                description=description,
                timeout=timeout,
            )
            return endpoint

        return decorator

    def stream_stream(
        self,
        name: Optional[str] = None,
        *,
        request_model: Optional[Type[BaseModel]] = None,
        response_model: Optional[Type[BaseModel]] = None,
        description: str = "",
        timeout: Optional[float] = None,
    ):
        def decorator(endpoint: Callable) -> Callable:
            self.service.add_method(
                name=name,
                endpoint=endpoint,
                method_class=StreamStreamMethod,
                request_model=request_model,
                response_model=response_model,
                description=description,
                timeout=timeout,
            )
            return endpoint

        return decorator

    def run(
        self,
        host: str = "127.0.0.1",
        port: int = 50051,
        server: Optional[Server] = None,
        reflection_enable: bool = True,
        health_check: bool = False,
        ssl_certificate_chain: Optional[str] = None,
        ssl_private_key: Optional[str] = None,
        ca_certificate: Optional[str] = None,
        graceful_timeout: Optional[float] = None,
    ) -> None:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            self.run_async(
                host=host,
                port=port,
                server=server,
                reflection_enable=reflection_enable,
                health_check=health_check,
                ssl_certificate_chain=ssl_certificate_chain,
                ssl_private_key=ssl_private_key,
                ca_certificate=ca_certificate,
                graceful_timeout=graceful_timeout,
            )
        )
        loop.close()

    async def run_async(
        self,
        host: str = "127.0.0.1",
        port: int = 50051,
        server: Optional[Server] = None,
        reflection_enable: bool = True,
        health_check: bool = False,
        ssl_certificate_chain: Optional[str] = None,
        ssl_private_key: Optional[str] = None,
        ca_certificate: Optional[str] = None,
        graceful_timeout: Optional[float] = None,
    ) -> None:
        server = grpc.aio.server() if not server else server

        if ssl_certificate_chain and ssl_private_key:
            if not ssl_certificate_chain or not ssl_private_key:
                raise ValueError(
                    "Both ssl_certificate_chain and ssl_private_key must be provided for TLS"
                )
            with open(ssl_certificate_chain, "rb") as f:
                cert_chain = f.read()
            with open(ssl_private_key, "rb") as f:
                private_key = f.read()
            root_certificates = None
            require_client_auth = False
            if ca_certificate:
                with open(ca_certificate, "rb") as f:
                    root_certificates = f.read()
                require_client_auth = True
            credentials = grpc.ssl_server_credentials(
                [(private_key, cert_chain)],
                root_certificates=root_certificates,
                require_client_auth=require_client_auth,
            )
            server.add_secure_port(f"{host}:{port}", credentials)
        elif bool(ssl_certificate_chain) != bool(ssl_private_key):
            raise ValueError(
                "Both ssl_certificate_chain and ssl_private_key must be provided together"
            )
        else:
            server.add_insecure_port(f"{host}:{port}")

        self.add_to_server(server)
        if reflection_enable:
            self.enable_server_reflection(server)
        if health_check:
            try:
                from grpc_health.v1 import health_pb2, health_pb2_grpc
            except ImportError:
                raise ImportError(
                    "health_check=True requires grpcio-health-checking. "
                    "Install it with: pip install grpcio-health-checking"
                )
            health_servicer = health_pb2_grpc.HealthServicer()
            health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
            for svc in self._services.values():
                if svc.grpc_servicer:
                    health_servicer.set(
                        svc.get_pb_full_name(),
                        health_pb2.HealthCheckResponse.SERVING,
                    )
        await server.start()
        logger.info(f"Running grpc on {host}:{port}")

        if graceful_timeout is not None:
            stop_event = asyncio.Event()

            def _signal_handler():
                logger.info("Shutting down gracefully...")
                stop_event.set()

            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.add_signal_handler(sig, _signal_handler)
                except NotImplementedError:
                    logger.warning(
                        f"Signal handler for {sig.name} not supported on this platform"
                    )

            await stop_event.wait()
            await server.stop(graceful_timeout)
            logger.info("Server stopped gracefully")
        else:
            await server.wait_for_termination()

    def add_service(self, service: BaseService) -> None:
        if isinstance(service, Service):
            if not service.proto:
                service.proto = self.service.proto
        if service.full_name not in self._services:
            self._services[service.full_name] = service.copy()
        self._services[service.full_name].methods.update(service.methods)

    def add_to_server(self, server: Server):
        self.setup()
        # Resolve timeouts: method > service > global
        for svc in self._services.values():
            svc_timeout = getattr(svc, 'timeout', None)
            for method in svc.methods.values():
                if method.timeout is None:
                    method.timeout = svc_timeout or self._timeout
        for service in self._services.values():
            service.add_to_server(
                server, self._middlewares, self._server_streaming_middlewares
            )

    def enable_server_reflection(self, server: Server):
        service_names = [
            service.get_pb_full_name()
            for service in self._services.values()
            if service.grpc_servicer
        ]
        service_names.append(reflection.SERVICE_NAME)
        reflection.enable_server_reflection(service_names, server)
