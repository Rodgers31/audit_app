"""Outside-root read-only kernel observer; no production values or routing.

Runs in the fixture's private network, with all capabilities dropped. The sole
pre-isolation listening socket serves a fixed maintenance page. App/native code
inherits no listener, directory, proc or cgroup descriptors.
"""
import hashlib
import json
import os
from pathlib import Path
import selectors
import socket
import sys
import time


def observe(listener, identity):
    from isolation import drop_capabilities, require
    drop_capabilities()
    # Entry deliberately uses -I/-S; add only this image's public locked deps.
    sys.path.insert(0, '/usr/local/lib/python3.12/site-packages')
    import psutil
    from confinement import install
    require(install(observer=True).get('kind') == 'landlock-seccomp',
            'Observer confinement refused')
    out = Path('/evidence')
    group = Path('/sys/fs/cgroup')
    producer = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    started, sampled, sequence = time.monotonic(), 0.0, 0
    selector = selectors.DefaultSelector()
    selector.register(listener, selectors.EVENT_READ)
    while True:
        now = time.monotonic()
        # Bound the maintenance fixture to ten minutes, including operator
        # wait. A timeout is FAIL, never a substitute for Render stop proof.
        if now - started > 600:
            print('HOST_FIXTURE_ABORT maintenance_deadline', flush=True)
            os.kill(1, 15)
            raise RuntimeError('Maintenance deadline')
        if now - sampled >= 1:
            processes = []
            for proc in psutil.process_iter():
                try:
                    argv, rss = proc.cmdline(), proc.memory_info().rss
                    if argv and rss > 0:
                        processes.append(dict(pid=proc.pid, ppid=proc.ppid(), argv=argv,
                            rss=rss, threads=proc.num_threads()))
                except (psutil.NoSuchProcess, psutil.ZombieProcess):
                    pass
            sequence += 1
            value = dict(generator_sha256=producer, run_id=identity['run_id'],
                manifest_sha256=identity['manifest_sha256'], sequence=sequence,
                observed_at=now, memory=int((group / 'memory.current').read_text()),
                peak=int((group / 'memory.peak').read_text()),
                cpu=dict(line.split() for line in (group / 'cpu.stat').read_text().splitlines()),
                oom=dict(line.split() for line in (group / 'memory.events').read_text().splitlines()),
                processes=processes)
            raw = json.dumps(value, allow_nan=False, sort_keys=True)
            temp = out / 'metrics.pending'
            temp.write_text(raw)
            temp.replace(out / 'metrics.json')
            require(json.loads((out / 'metrics.json').read_text()) == value, 'Metrics readback differs')
            sampled = now
            if value['memory'] >= 480 * 1024 ** 2 or int(value['oom']['oom_kill']) != 0:
                print('HOST_FIXTURE_ABORT memory_or_oom', flush=True)
                os.kill(1, 15)
                raise RuntimeError('Memory/OOM abort')
        for key, _ in selector.select(.2):
            if key.fileobj is listener:
                conn, _ = listener.accept()
                try:
                    conn.settimeout(.3)
                    request = conn.recv(4096)
                    # This health endpoint means fixture liveness only. All
                    # normal paths, including API readiness, remain 503.
                    healthy = request.startswith(b'GET /fixture-health HTTP/1.')
                    status = b'200 OK' if healthy else b'503 Service Unavailable'
                    body = b'AuditGava maintenance fixture\n'
                    conn.sendall(b'HTTP/1.1 ' + status + b'\r\nConnection: close\r\n'
                        b'Content-Type: text/plain\r\nCache-Control: no-store\r\n'
                        b'Content-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
                except (OSError, TimeoutError):
                    pass
                finally:
                    conn.close()
