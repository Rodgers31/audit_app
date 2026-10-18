"""Count actual PostgreSQL protocol bytes; never log payloads or proxy public DBs."""
import json
import select
import socket
import threading
import time

totals = dict(client_bytes=0, server_bytes=0, connections=0, active=0, peak_active=0, upstream_failures=0)
lock = threading.Lock()


def serve(client):
    upstream = None
    with lock:
        totals['connections'] += 1
        totals['active'] += 1
        totals['peak_active'] = max(totals['peak_active'], totals['active'])
    try:
        try:
            upstream = socket.create_connection(('b15-worker-db', 5432), timeout=5)
            upstream.settimeout(None)
        except OSError:
            with lock:
                totals['upstream_failures'] += 1
            return
        while True:
            readable, _, _ = select.select([client, upstream], [], [], 1)
            for source in readable:
                data = source.recv(65536)
                if not data:
                    return
                destination = upstream if source is client else client
                destination.sendall(data)
                with lock:
                    totals['client_bytes' if source is client else 'server_bytes'] += len(data)
    finally:
        try:
            client.close()
        finally:
            try:
                if upstream is not None:
                    upstream.close()
            finally:
                with lock:
                    totals['active'] -= 1


def report():
    while True:
        with lock:
            print(json.dumps(dict(wire=True, monotonic=time.monotonic(), **totals)), flush=True)
        time.sleep(1)


threading.Thread(target=report, daemon=True).start()
listener = socket.socket()
listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
listener.bind(('0.0.0.0', 5432))
listener.listen(8)
while True:
    child, _ = listener.accept()
    threading.Thread(target=serve, args=(child,), daemon=True).start()
