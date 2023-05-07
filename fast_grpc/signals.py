from blinker import Namespace

_signals = Namespace()

rpc_startup = _signals.signal("startup")
rpc_shutdown = _signals.signal("shutdown")
