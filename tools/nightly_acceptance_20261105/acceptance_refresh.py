"""Actual loopback serving census, signed refresh capture and offline verification.

No production host or key is discovered. Callers explicitly supply a test secret
and own the serving processes. Historical verification checks cryptography and
semantics; it is never relabelled as a new serving-host observation.
"""
from datetime import datetime, timezone
import hashlib
import hmac
import http.client
import os
from pathlib import Path
import re
import socket
import time

from common import (BoundEvidence, Refusal, canonical, digest, fields, integer, loads,
                    publish, require, string)

ROOT = Path(__file__).absolute().parents[2]
PATHS = ROOT / 'frontend/lib/revalidation/paths.json'


def binding(value):
    fields(value, ('commit', 'run_id', 'attempt'))
    digest(value['commit'], 40); integer(value['run_id'], 1); integer(value['attempt'], 1)
    return value


def signing_key(secret):
    require(type(secret) is bytes and 32 <= len(secret) <= 1024, 'explicit bounded signing key bytes required')
    return secret


def _pid(pid):
    integer(pid, 2)
    raw = Path('/proc', str(pid), 'stat').read_text()
    after = raw.rsplit(')', 1)[1].split()
    return int(after[1]), int(after[19])  # ppid and Linux starttime, not wall-clock guesses


def observe_workers(supervisor_pid, port, expected_workers):
    """Enumerate the owned supervisor's actual live listener holders on Linux."""
    integer(supervisor_pid, 2); integer(port, 1024); integer(expected_workers, 1)
    require(port <= 65535 and expected_workers <= 16, 'bounded loopback census required')
    require(Path('/proc/net/tcp').is_file(), 'Linux serving-process census capability required')
    parent, supervisor_start = _pid(supervisor_pid)
    require(parent == os.getpid(), 'serving supervisor must be this collector process child')
    command = Path('/proc', str(supervisor_pid), 'cmdline').read_bytes()
    require(b'uvicorn' in command or b'gunicorn' in command, 'actual serving supervisor command required')
    inodes = {row.split()[9] for row in Path('/proc/net/tcp').read_text().splitlines()[1:]
              if row.split()[1] == '0100007F:' + format(port, '04X') and row.split()[3] == '0A'}
    require(len(inodes) == 1, 'exact loopback serving listener required')
    processes = {}
    for path in Path('/proc').iterdir():
        if path.name.isdecimal():
            try: processes[int(path.name)] = _pid(int(path.name))
            except (OSError, ValueError, IndexError): pass  # exited during census, rechecked below
    require(len(processes) <= 256, 'process census ceiling')
    descendants = {supervisor_pid}
    while True:
        expanded = descendants | {pid for pid, (ppid, _) in processes.items() if ppid in descendants}
        if expanded == descendants: break
        descendants = expanded
    workers = []
    for pid in sorted(descendants - {supervisor_pid}):
        try:
            links = {os.readlink(fd) for fd in Path('/proc', str(pid), 'fd').iterdir()}
            if any('socket:[' + inode + ']' in links for inode in inodes):
                workers.append({'pid': pid, 'start_ticks': processes[pid][1]})
        except OSError as exc:
            raise Refusal('serving census changed during observation') from exc
    require(len(workers) == expected_workers, 'actual serving worker census incomplete')
    require(_pid(supervisor_pid) == (parent, supervisor_start)
            and all(_pid(w['pid'])[1] == w['start_ticks'] for w in workers), 'serving process identity changed')
    return {'supervisor_pid': supervisor_pid, 'supervisor_start_ticks': supervisor_start,
            'port': port, 'listener_inode': next(iter(inodes)), 'workers': workers}


def _census(value):
    fields(value, ('supervisor_pid', 'supervisor_start_ticks', 'port', 'listener_inode', 'workers'))
    integer(value['supervisor_pid'], 2); integer(value['supervisor_start_ticks'], 1)
    integer(value['port'], 1024); require(value['port'] <= 65535, 'invalid census port')
    require(type(value['listener_inode']) is str and value['listener_inode'].isdecimal(), 'listener identity required')
    require(type(value['workers']) is list and 1 <= len(value['workers']) <= 16, 'actual worker census required')
    pids = []
    for row in value['workers']:
        fields(row, ('pid', 'start_ticks'))
        pids.append(integer(row['pid'], 2)); integer(row['start_ticks'], 1)
    require(len(set(pids)) == len(pids), 'duplicate serving worker')
    return set(pids)


def _paths():
    with BoundEvidence() as original:
        value = original.json(PATHS)
    require(type(value) is dict and type(value.get('paths')) is list and bool(value['paths'])
            and all(type(p) is str and p.startswith('/') for p in value['paths'])
            and len(set(value['paths'])) == len(value['paths']), 'source frontend path allowlist unavailable')
    return value['paths']


def _reference(path):
    body = path.read_bytes()
    return {'path': path.name, 'sha256': hashlib.sha256(body).hexdigest(), 'size': len(body)}


def _body(originals, root, reference):
    from operational import artifact
    path = artifact(reference, root, originals)
    body = originals.read(path)
    require(len(body) <= 131072, 'refresh original body byte ceiling')
    return body


def invalidation_response(response, pids, reason):
    require(type(response) is dict and response.get('invalidated') is True
            and response.get('reason') == reason
            and type(response.get('pid')) is int and response['pid'] in pids
            and type(response.get('generation')) is str
            and re.fullmatch('[0-9a-f]{32}', response['generation']) is not None,
            'backend invalidation response has no actual generation')
    marker = response.get('marker_identity')
    require(type(marker) is list and len(marker) == 3 and all(type(x) is int and x > 0 for x in marker),
            'backend marker identity required')
    require(type(response.get('redis')) is dict and set(response['redis']) == {'configured','deleted'}
            and type(response['redis']['configured']) is bool
            and type(response['redis']['deleted']) is int and response['redis']['deleted'] >= 0
            and type(response.get('local')) is dict and type(response['local'].get('cleared_entries')) is int
            and response['local']['cleared_entries'] >= 0 and type(response['local'].get('by_cache')) is dict
            and bool(response['local']['by_cache'])
            and all(type(v) is int and v >= 0 for v in response['local']['by_cache'].values())
            and sum(response['local']['by_cache'].values()) == response['local']['cleared_entries'],
            'cache layer observations required')
    return marker


def worker_response(response, pids, acknowledged, marker, commit):
    require(type(response) is dict, 'actual worker response required')
    pid = response.get('pid')
    require(type(pid) is int and pid in pids and pid not in acknowledged
            and response.get('commit') == commit and response.get('synchronised') is True
            and canonical(response.get('observed_identity')) == canonical(marker)
            and canonical(response.get('adopted_identity')) == canonical(marker)
            and type(response.get('marker_path')) is str and response['marker_path'].startswith('/'),
            'worker adoption missing/duplicate/wrong-source/stale')
    return pid


class DeadlineSocket(socket.socket):
    """SocketIO calls recv_into for headers and bodies; every call shares a deadline."""
    def __init__(self, deadline):
        super().__init__(socket.AF_INET, socket.SOCK_STREAM)
        self.deadline = deadline

    def check(self):
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, 'refresh absolute deadline')
        self.settimeout(min(2, remaining))

    def recv_into(self, *args, **kwargs):
        self.check()
        result = super().recv_into(*args, **kwargs)
        self.check()
        return result

    def sendall(self, *args, **kwargs):
        self.check()
        result = super().sendall(*args, **kwargs)
        self.check()
        return result


def verify_capture(path, *, secret, expected_binding, expected_census):
    """Verify exact retained requests, transcript seal, census and response semantics."""
    signing_key(secret); binding(expected_binding); pids = _census(expected_census)
    with BoundEvidence() as originals:
        value = originals.json(path)
        fields(value, ('schema', 'binding', 'census', 'started_at', 'finished_at', 'paths', 'events', 'seal'))
        require(value['schema'] == 'nightly-refresh-capture-v1', 'unknown signed refresh capture')
        binding(value['binding']); _census(value['census'])
        require(canonical(value['binding']) == canonical(expected_binding)
                and canonical(value['census']) == canonical(expected_census), 'refresh run/source/census differs')
        for key in ('started_at', 'finished_at'):
            require(type(value[key]) in (int, float) and 0 < value[key] < float('inf'), 'finite capture time required')
        require(0 <= value['finished_at'] - value['started_at'] <= 60
                and 0 <= time.time() - value['finished_at'] <= 604800, 'stale/future/over-budget capture')
        payload = {k: v for k, v in value.items() if k != 'seal'}
        seal = hmac.new(secret, b'nightly-refresh-capture-v1\0' + canonical(payload), hashlib.sha256).hexdigest()
        require(hmac.compare_digest(digest(value['seal']), seal), 'invalid refresh transcript seal')
        require(value['paths'] == _paths(), 'frontend paths differ from exact source allowlist')
        require(type(value['events']) is list and len(value['events']) == len(pids) + 2,
                'signed backend/worker/frontend inventory incomplete')
        root = Path(path).absolute().parent
        kinds, acknowledged, marker = [], set(), None
        expected_reason = f"nightly-{expected_binding['run_id']}-{expected_binding['attempt']}-{expected_binding['commit']}"
        for index, event in enumerate(value['events']):
            fields(event, ('kind', 'sequence', 'request', 'response', 'signature', 'status', 'received_at'))
            require(type(event['sequence']) is int and event['sequence'] == index,
                    'duplicate/reordered signed refresh event')
            require(type(event['status']) is int and event['status'] == 200, 'refresh HTTP status refused')
            received = event['received_at']
            require(type(received) in (int, float) and value['started_at'] <= received <= value['finished_at'],
                    'event capture time outside original interval')
            raw = _body(originals, root, event['request'])
            require(hmac.compare_digest(digest(event['signature']), hmac.new(secret, raw, hashlib.sha256).hexdigest()),
                    'invalid request HMAC')
            request, response = loads(raw), loads(_body(originals, root, event['response']))
            require(type(request) is dict and type(response) is dict, 'actual JSON request/response required')
            ts = request.get('ts')
            require(type(ts) in (int, float) and abs(received - ts) <= 300,
                    'stale/malformed signed request time')
            binding(request.get('binding'))
            require(canonical(request['binding']) == canonical(expected_binding), 'signed request belongs to another run/source')
            kind = event['kind']; kinds.append(kind)
            if kind == 'backend_invalidate':
                require(index == 0 and request.get('reason') == expected_reason, 'invalidation order/reason differs')
                marker = invalidation_response(response, pids, expected_reason)
            elif kind == 'backend_worker':
                pid = worker_response(response, pids, acknowledged, marker, expected_binding['commit'])
                acknowledged.add(pid)
            elif kind == 'frontend':
                require(index == len(value['events']) - 1 and acknowledged == pids
                        and request.get('paths') == value['paths'] and response.get('rejected') == []
                        and response.get('revalidated') == value['paths']
                        and type(response.get('at')) is str, 'frontend ack incomplete or before backend adoption')
                at = datetime.fromisoformat(response['at'].replace('Z', '+00:00'))
                require(at.tzinfo is not None and abs(at.timestamp() - received) <= 300,
                        'frontend response time differs')
            else:
                require(False, 'unknown refresh event')
        require(kinds == ['backend_invalidate', *['backend_worker'] * len(pids), 'frontend']
                and acknowledged == pids, 'backend census must precede exact frontend pages')
    return {'verdict': 'OFFLINE_HMAC_AND_ACK_SEMANTICS_VERIFIED', 'production_accepted': False,
            'binding': expected_binding, 'worker_pids': sorted(pids), 'paths': value['paths']}


def capture_loopback(output, *, supervisor_pid, backend_port, frontend_port, expected_workers, secret, run_binding):
    """Call real local serving routes; an offline capture cannot invoke this observation."""
    from record import outside
    signing_key(secret); binding(run_binding); integer(frontend_port, 1024)
    require(frontend_port <= 65535 and frontend_port != backend_port, 'separate loopback frontend listener required')
    output = outside(output, [ROOT]); require(not output.exists(), 'fresh refresh originals directory required')
    before = observe_workers(supervisor_pid, backend_port, expected_workers)
    output.mkdir(mode=0o700)
    started = time.time(); deadline = time.monotonic() + 30
    events, attempts = [], 0
    def request(kind, port, path, extra):
        nonlocal attempts
        attempts += 1
        require(attempts <= 64, 'refresh request ceiling')
        require(time.monotonic() < deadline, 'refresh capture deadline')
        raw = canonical(dict(ts=time.time(), binding=run_binding, **extra))
        signature = hmac.new(secret, raw, hashlib.sha256).hexdigest()
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=min(2, max(.01, deadline-time.monotonic())))
        try:
            connection.sock = DeadlineSocket(deadline)
            connection.sock.check()
            connection.sock.connect(('127.0.0.1', port))
            connection.request('POST', path, raw, {'Content-Type':'application/json', 'x-revalidate-signature':signature,
                                                  'Connection':'close'})
            response = connection.getresponse(); body = response.read(131073)
            require(time.monotonic() < deadline, 'refresh absolute deadline')
            require(len(body) <= 131072 and response.status == 200, 'bounded successful refresh HTTP response required')
            status = response.status
        finally:
            connection.close()
        sequence = len(events)
        req, res = output / f'{sequence}-request.json', output / f'{sequence}-response.json'
        with req.open('xb') as stream: stream.write(raw)
        with res.open('xb') as stream: stream.write(body)
        event = dict(kind=kind, sequence=sequence, request=_reference(req), response=_reference(res),
                     signature=signature, status=status, received_at=time.time())
        return event, loads(body)
    reason = f"nightly-{run_binding['run_id']}-{run_binding['attempt']}-{run_binding['commit']}"
    event, result = request('backend_invalidate', backend_port, '/api/v1/system/cache/invalidate', {'reason':reason})
    pids = _census(before)
    marker = invalidation_response(result, pids, reason)
    events.append(event)
    seen = set()
    while seen != pids:
        require(time.monotonic() < deadline, 'serving worker acknowledgments timed out')
        event, response = request('backend_worker', backend_port, '/api/v1/system/cache/status', {})
        pid = worker_response(response, pids, set(), marker, run_binding['commit'])
        if pid in seen:
            # Retain diagnostic duplicate attempts separately; never count one
            # worker twice as a complete census. Originals are not rewritten.
            for key in ('request', 'response'):
                path = output / event[key]['path']
                path.rename(output / ('duplicate-' + str(time.monotonic_ns()) + '-' + path.name))
            time.sleep(.01)
            continue
        seen.add(pid); events.append(event)
    event, _ = request('frontend', frontend_port, '/api/revalidate', {'paths':_paths()})
    events.append(event)
    after = observe_workers(supervisor_pid, backend_port, expected_workers)
    require(before == after, 'serving worker census changed through refresh')
    value = dict(schema='nightly-refresh-capture-v1', binding=run_binding, census=before,
                 started_at=started, finished_at=time.time(), paths=_paths(), events=events)
    value['seal'] = hmac.new(secret, b'nightly-refresh-capture-v1\0' + canonical(value), hashlib.sha256).hexdigest()
    publish(output / 'refresh.json', value)
    verified = verify_capture(output / 'refresh.json', secret=secret,
                              expected_binding=run_binding, expected_census=before)
    return dict(verified, verdict='LOCAL_SERVING_SIGNED_REFRESH_OBSERVED')
