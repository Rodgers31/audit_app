"""Small HTTPS issuer downloads with pinned public DNS and a shared deadline.

Only the two reviewed Let's Encrypt distribution files used by the KNBS chain
are admitted. Legacy HTTP AIA identifiers select these HTTPS files; they never
cause an HTTP request. Redirects and content encodings are refused.
"""
from __future__ import annotations

import ipaddress
import json
import math
import socket
import ssl
import subprocess
import sys
import time

import certifi
import httpcore

MAX_CERT_BYTES = 16 * 1024
MAX_WIRE_BYTES = 32 * 1024  # Includes HTTP headers and chunk framing.
MAX_SECONDS = 10.0
MAX_FETCHES = 5

_FILES = {
    'ye2': 'https://letsencrypt.org/certs/gen-y/int-ye2.der',
    'ye': 'https://letsencrypt.org/certs/gen-y/root-ye-by-x2.der',
}
_URLS = {url: url for url in _FILES.values()}
_URLS.update({f'{scheme}://{name}.i.lencr.org/': url
              for name, url in _FILES.items() for scheme in ('http', 'https')})

# getaddrinfo has no portable timeout. A short-lived isolated child lets us
# kill and reap a stalled lookup rather than accumulating resolver threads.
_RESOLVE = """
import json, socket, sys
rows = socket.getaddrinfo(sys.argv[1], 443, type=socket.SOCK_STREAM)
addresses = sorted({row[4][0] for row in rows})
if not 0 < len(addresses) <= 16:
    raise ValueError('DNS answer count')
print(json.dumps(addresses))
"""


class IssuerRefused(ValueError):
    """No safe bounded issuer response is available."""


def remaining(deadline: float) -> float:
    value = deadline - time.monotonic()
    if not math.isfinite(value) or not 0 < value <= MAX_SECONDS:
        raise IssuerRefused('issuer deadline exceeded')
    return value


def _public_addresses(host: str, deadline: float) -> list[str]:
    result = subprocess.run(
        [sys.executable, '-I', '-c', _RESOLVE, host],
        env={}, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        timeout=min(2.0, remaining(deadline)), check=True,
    )
    remaining(deadline)
    addresses = json.loads(result.stdout)
    if not isinstance(addresses, list) or not 0 < len(addresses) <= 16:
        raise IssuerRefused('invalid DNS answer')
    for value in addresses:
        address = ipaddress.ip_address(value)
        if (not address.is_global or address.is_multicast or address.is_reserved
                or getattr(address, 'ipv4_mapped', None) is not None):
            raise IssuerRefused('non-public DNS answer')
    return addresses


def connect_public(host: str, deadline: float) -> socket.socket:
    """Connect to an admitted numeric address, without a second DNS lookup."""
    if host not in {'letsencrypt.org', 'knbs.or.ke', 'www.knbs.or.ke'}:
        raise IssuerRefused('unapproved certificate host')
    addresses = _public_addresses(host, deadline)
    for address in addresses:
        family = socket.AF_INET6 if ':' in address else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            sock.settimeout(min(2.0, remaining(deadline)))
            sock.connect((address, 443))
            remaining(deadline)
            return sock
        except OSError:
            sock.close()
        except BaseException:
            sock.close()
            raise
    raise IssuerRefused('no public address connected')


class _DeadlineStream(httpcore.NetworkStream):
    def __init__(self, sock: socket.socket, deadline: float):
        self.sock, self.deadline, self.received = sock, deadline, 0

    def read(self, max_bytes: int, timeout=None) -> bytes:
        self.sock.settimeout(min(2.0, remaining(self.deadline)))
        data = self.sock.recv(min(max_bytes, 1024, MAX_WIRE_BYTES - self.received + 1))
        remaining(self.deadline)
        self.received += len(data)
        if self.received > MAX_WIRE_BYTES:
            raise IssuerRefused('issuer wire byte limit exceeded')
        return data

    def write(self, buffer: bytes, timeout=None) -> None:
        while buffer:
            self.sock.settimeout(min(2.0, remaining(self.deadline)))
            sent = self.sock.send(buffer)
            if sent <= 0:
                raise IssuerRefused('issuer connection closed during write')
            buffer = buffer[sent:]
        remaining(self.deadline)

    def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        try:
            if (server_hostname != 'letsencrypt.org' or not ssl_context.check_hostname
                    or ssl_context.verify_mode != ssl.CERT_REQUIRED):
                raise IssuerRefused('issuer TLS verification required')
            self.sock.settimeout(min(2.0, remaining(self.deadline)))
            self.sock = ssl_context.wrap_socket(self.sock, server_hostname=server_hostname)
            remaining(self.deadline)
            return self
        except BaseException:
            self.close()
            raise

    def close(self):
        self.sock.close()

    def get_extra_info(self, info):
        if info == 'ssl_object':
            return self.sock if isinstance(self.sock, ssl.SSLSocket) else None
        return None


class _IssuerBackend(httpcore.NetworkBackend):
    def __init__(self, deadline):
        self.deadline = deadline

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if host != 'letsencrypt.org' or port != 443:
            raise IssuerRefused('unapproved issuer connection')
        return _DeadlineStream(connect_public(host, self.deadline), self.deadline)


def fetch_issuer_bytes(url: str, deadline: float) -> bytes:
    target = _URLS.get(url)
    if target is None:
        raise IssuerRefused('unapproved issuer URL')
    remaining(deadline)
    with httpcore.ConnectionPool(
        ssl_context=ssl.create_default_context(cafile=certifi.where()),
        network_backend=_IssuerBackend(deadline), max_connections=1,
        max_keepalive_connections=0, retries=0,
    ) as pool:
        with pool.stream('GET', target, headers={
            'Accept-Encoding': 'identity', 'Connection': 'close',
        }) as response:
            remaining(deadline)
            if response.status != 200:
                raise IssuerRefused('issuer response must be 200; redirects refused')
            headers = {key.lower(): value for key, value in response.headers}
            if any(key.lower() == b'content-encoding' and value.lower() != b'identity'
                   for key, value in response.headers):
                raise IssuerRefused('encoded issuer response refused')
            length = headers.get(b'content-length')
            if length is not None and (not length.isdigit() or int(length) > MAX_CERT_BYTES):
                raise IssuerRefused('issuer declared byte limit exceeded')
            payload = bytearray()
            for chunk in response.iter_stream():
                remaining(deadline)
                if len(payload) + len(chunk) > MAX_CERT_BYTES:
                    raise IssuerRefused('issuer actual byte limit exceeded')
                payload.extend(chunk)
            remaining(deadline)
            return bytes(payload)
