# -*- coding: utf-8 -*-
from typing import Optional

import grpc
from grpc._typing import MetadataType


class RPCException(grpc.RpcError):
    def __init__(
        self,
        code: grpc.StatusCode,
        detail: Optional[str] = None,
        trailing_metadata: Optional[MetadataType] = None,
    ) -> None:
        if detail is None:
            detail = code.value[1]
        self.code = code
        self.detail = detail
        self.trailing_metadata = trailing_metadata

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        return f"{class_name}(code={self.code.value[0]}, detail={self.detail!r})"


class Error(grpc.Status):
    def __init__(
        self, code: grpc.StatusCode, details: Optional[str] = None, trailing_metadata: Optional[MetadataType] = None
    ):
        if details is None:
            details = code.value[1]
        self.code = code
        self.details = details
        self.trailing_metadata = trailing_metadata
