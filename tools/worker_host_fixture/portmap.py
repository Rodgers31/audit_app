"""Private fixture translation: TLS443 to unprivileged loopback8443.

No capability or host sysctl is retained/changed to serve synthetic TLS. URL,
SNI, certificate, SDK and HTTP payload remain; TCP port parity is not claimed.
"""
import socket


def destination(address):
    if (type(address) is tuple and len(address) == 2 and type(address[0]) is str and address[0] == '127.0.0.4'
            and type(address[1]) is int and address[1] == 443):
        return ('127.0.0.4', 8443)
    return address


def install():
    if getattr(socket.socket, '_host_fixture_portmap', False):
        raise RuntimeError('Duplicate private port translation')
    original_connect, original_ex = socket.socket.connect, socket.socket.connect_ex
    def connect(self, address):
        return original_connect(self, destination(address))
    def connect_ex(self, address):
        return original_ex(self, destination(address))
    socket.socket.connect, socket.socket.connect_ex = connect, connect_ex
    socket.socket._host_fixture_portmap = True


def endpoint_server(address, handler, original):
    if (type(address) is not tuple or len(address) != 2 or type(address[0]) is not str
            or address[0] != '127.0.0.4' or type(address[1]) is not int or address[1] != 443):
        raise ValueError('Fixed private endpoint bind required')
    server = original(('127.0.0.4', 8443), handler)
    # Only the synthetic image server has just generated a27MiB random image
    # to prewarm its JPEG bytes. Return its freed temporary heap to glibc;
    # never change the allocator behavior of the real API/native processes.
    trim_inert_heap()
    return server


def trim_inert_heap():
    import ctypes
    library = ctypes.CDLL(None)
    library.malloc_trim.argtypes = [ctypes.c_size_t]
    library.malloc_trim.restype = ctypes.c_int
    result = library.malloc_trim(0)
    if type(result) is not int or result not in (0, 1):
        raise RuntimeError('Unexpected inert allocator result')
