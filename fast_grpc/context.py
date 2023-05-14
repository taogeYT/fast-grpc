from grpc._cython import cygrpc


class ServicerContext:
    def __init__(self, context: cygrpc._SyncServicerContext, method):
        self.rpc_context = context
        self.method = method
