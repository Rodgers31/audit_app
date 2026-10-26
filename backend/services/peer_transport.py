"""Bounded reads of the two fixed, public regional-observation providers."""
import json
import time
from contextvars import ContextVar

import httpx

MAX_BYTES = 1024 * 1024
READ_SECONDS = 1.0
TOTAL_SECONDS = 8.0
peer_deadline = ContextVar('peer_observation_deadline', default=None)


def read_json(url):
    deadline = peer_deadline.get()
    if deadline is None:
        deadline = time.monotonic() + TOTAL_SECONDS
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise httpx.ReadTimeout('Peer observation time budget exceeded')
    # Fixed URLs at the caller; no environment proxy, credentials or redirects.
    with httpx.Client(trust_env=False, follow_redirects=False,
                      timeout=httpx.Timeout(min(READ_SECONDS, remaining)),
                      limits=httpx.Limits(max_connections=1, max_keepalive_connections=0)) as client:
        with client.stream('GET', url, headers={'Accept-Encoding': 'identity', 'Accept': 'application/json'}) as response:
            response.raise_for_status()
            if response.headers.get('content-encoding', 'identity').strip().lower() != 'identity':
                raise ValueError('Peer observation encoding exceeds supported budget')
            declared = response.headers.get('content-length')
            if declared is not None and (not declared.isascii() or not declared.isdigit() or int(declared) > MAX_BYTES):
                raise ValueError('Peer observation byte budget exceeded')
            body = bytearray()
            for chunk in response.iter_raw():
                if time.monotonic() >= deadline:
                    raise httpx.ReadTimeout('Peer observation time budget exceeded')
                if len(body) + len(chunk) > MAX_BYTES:
                    raise ValueError('Peer observation byte budget exceeded')
                body.extend(chunk)
            if time.monotonic() >= deadline:
                raise httpx.ReadTimeout('Peer observation time budget exceeded')
            # UTF-8 only; no implicit UTF-16/32 or decompression expansion.
            return json.loads(body.decode('utf-8-sig'))
