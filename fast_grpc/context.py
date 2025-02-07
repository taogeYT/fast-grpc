import time

import grpc
from typing import List, Tuple


class ServiceContext:
    def __init__(self, grpc_context: grpc.ServicerContext, method, method_descriptor):
        self.grpc_context = grpc_context
        self.service_method = method
        self.method_descriptor = method_descriptor
        self.input_type = method_descriptor.input_type._concrete_class
        self.output_type = method_descriptor.output_type._concrete_class
        self._start_time = time.time()
        self._metadata: dict[str, str] = {}

    @property
    def elapsed_time(self):
        return int(time.time() - self._start_time) * 1000

    @property
    def metadata(self) -> dict[str, str]:
        if not self._metadata:
            self._metadata = dict(self.grpc_context.invocation_metadata())
        return self._metadata

    def is_active(self) -> bool:
        return self.grpc_context.is_active()

    def time_remaining(self) -> float:
        return self.grpc_context.time_remaining()

    def invocation_metadata(self) -> List[Tuple[str, str]]:
        return self.grpc_context.invocation_metadata()

    def peer(self) -> str:
        return self.grpc_context.peer()

    def abort(self, code: grpc.StatusCode, details: str):
        return self.grpc_context.abort(code, details)

    def abort_with_status(self, status: grpc.Status):
        return self.grpc_context.abort_with_status(status)

    def set_code(self, code: grpc.StatusCode):
        return self.grpc_context.set_code(code)

    def set_details(self, details: str):
        return self.grpc_context.set_details(details)
