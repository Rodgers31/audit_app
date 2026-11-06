"""Strict signed cache adoption before exact-page revalidation.

This client cannot execute ingestion or publishing. It consumes already-verified
workflow eligibility and uses only the existing signed cache endpoints. A
container census is meaningful only with separately verified single-instance
serving topology; it does not discover other hosts behind a load balancer.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

PROTOCOL = 'nightly-refresh-v2'
MAX_BYTES = 65536
MAX_REQUESTS = 64


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def load(raw):
    require(len(raw) <= MAX_BYTES, 'response exceeds bound')
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def context_valid(context):
    return (type(context) is dict and set(context) == {'source_sha', 'plan_sha256', 'run_id', 'run_attempt', 'schema_head'}
            and all(type(context[k]) is str and re.fullmatch(pattern, context[k]) for k, pattern in {
                'source_sha': '[0-9a-f]{40}', 'plan_sha256': '[0-9a-f]{64}',
                'run_id': '[1-9][0-9]{0,17}', 'run_attempt': '[1-9][0-9]{0,4}'}.items())
            and context['schema_head'] == 'a756b20a0001')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('refresh redirect refused')


def private_evidence_fd(path, flags):
    """Anchor each directory before opening a private, bounded evidence leaf."""
    path = Path(path)
    require(path.is_absolute() and path.name and '..' not in path.parts,
            'absolute private evidence path required')
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    directory = os.open(path.anchor, directory_flags)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(path.name, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
    finally:
        os.close(directory)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.geteuid()
                and info.st_mode & 0o077 == 0 and info.st_size <= 8_000_000,
                'private bounded regular evidence file required')
    except BaseException:
        os.close(fd)
        raise
    return fd


class SignedClient:
    def __init__(self, secret, context, evidence, *, clock=time.monotonic, now=time.time):
        require(type(secret) is str and bool(secret), 'signing secret missing')
        require(context_valid(context), 'refresh context refused')
        self.secret, self.context, self.evidence = secret, context, evidence
        self.clock, self.now = clock, now
        self.deadline, self.requests = clock() + 90, 0
        self.opener = build_opener(NoRedirect(), ProxyHandler({}))

    def remaining(self):
        remaining = self.deadline - self.clock()
        require(remaining > 0, 'refresh deadline exceeded')
        return min(6, remaining)

    def post(self, url, **payload):
        parsed = urlsplit(url)
        require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and
                not parsed.password and not parsed.query and not parsed.fragment, 'refresh URL refused')
        require(self.requests < MAX_REQUESTS, 'refresh request allowance exceeded')
        self.requests += 1
        request = {'protocol': PROTOCOL, 'ts': int(self.now()), 'nonce': secrets.token_hex(16),
                   'context': self.context, **payload}
        raw = json.dumps(request, separators=(',', ':'), allow_nan=False).encode()
        sig = hmac.new(self.secret.encode(), raw, hashlib.sha256).hexdigest()
        req = Request(url, raw, {'content-type': 'application/json', 'accept-encoding': 'identity',
                                'x-revalidate-signature': sig}, method='POST')
        with self.opener.open(req, timeout=self.remaining()) as response:
            require(response.status == 200 and response.headers.get('content-encoding', 'identity') == 'identity',
                    'refresh HTTP status/encoding refused')
            chunks, size = [], 0
            while True:
                self.remaining()
                chunk = response.read1(min(16384, MAX_BYTES + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                require(size <= MAX_BYTES, 'refresh response exceeds bound')
                chunks.append(chunk)
            body = b''.join(chunks)
            signature = response.headers.get('x-revalidate-response-signature', '')
        # Retain originals even when subsequent signature/semantic checks refuse.
        record = {'request_base64': base64.b64encode(raw).decode('ascii'), 'request_sha256': hashlib.sha256(raw).hexdigest(),
                  'response_base64': base64.b64encode(body).decode('ascii'), 'response_sha256': hashlib.sha256(body).hexdigest(),
                  'request_signature': sig,
                  'response_signature': signature, 'url': url, 'http_status': 200}
        encoded = json.dumps(record, separators=(',', ':')).encode()
        fd = private_evidence_fd(self.evidence, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
        try:
            info = os.fstat(fd)
            require(info.st_size + len(encoded) + 1 <= 8_000_000,
                    'private bounded regular evidence file required')
            with os.fdopen(fd, 'ab', closefd=False) as stream:
                stream.write(encoded + b'\n')
        finally:
            os.close(fd)
        # A request HMAC is a replay capability during the timestamp window.
        # Public logs retain authenticated ciphertext, never that capability.
        try:
            sealed = subprocess.run(['node', str(Path(__file__).with_name('evidence.cjs')), 'seal'],
                input=encoded, capture_output=True, timeout=4,
                env={'PATH': os.environ['PATH'], 'REVALIDATE_SECRET': self.secret})
        except subprocess.SubprocessError:
            raise ValueError('Evidence encryption unavailable') from None
        require(sealed.returncode == 0 and len(sealed.stdout) <= 196608, 'evidence encryption refused')
        envelope = json.loads(sealed.stdout, object_pairs_hook=pairs)
        require(type(envelope) is dict and set(envelope) == {'schema','algorithm','nonce','ciphertext','tag','plaintext_sha256'}
                and envelope['schema'] == 'nightly-refresh-sealed-evidence-v1' and envelope['algorithm'] == 'aes-256-gcm'
                and envelope['plaintext_sha256'] == hashlib.sha256(encoded).hexdigest(), 'sealed evidence identity refused')
        print('REFRESH_HTTP_EVIDENCE_V2 ' + json.dumps(envelope, separators=(',', ':')))
        expected = hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        require(type(signature) is str and hmac.compare_digest(signature, expected), 'unsigned/invalid refresh response')
        ack = load(body)
        require(type(ack) is dict and set(ack) == {'protocol', 'context', 'request_sha256', 'at', 'result'}
                and ack['protocol'] == PROTOCOL and ack['context'] == self.context
                and ack['request_sha256'] == hashlib.sha256(raw).hexdigest()
                and type(ack['at']) is int and abs(self.now() - ack['at']) <= 300
                and type(ack['result']) is dict, 'refresh response identity refused')
        self.remaining()
        return ack['result']


def census_key(census):
    require(type(census) is dict and set(census) == {'scope', 'instance', 'supervisor', 'workers', 'worker'}
            and census['scope'] == 'container' and type(census['instance']) is str
            and re.fullmatch('[0-9a-f]{64}', census['instance']) is not None, 'serving census refused')
    def identity(value):
        return type(value) is str and re.fullmatch('[1-9][0-9]{0,9}:[1-9][0-9]{0,19}', value) is not None
    workers = census['workers']
    require(identity(census['supervisor']) and type(workers) is list and 1 <= len(workers) <= 64
            and all(identity(worker) for worker in workers) and len(set(workers)) == len(workers)
            and workers == sorted(workers) and census['worker'] in workers, 'serving worker inventory refused')
    return {k: census[k] for k in ('scope', 'instance', 'supervisor', 'workers')}


def marker_valid(marker):
    return type(marker) is list and len(marker) == 3 and all(type(n) is int and n > 0 for n in marker)


def adopt_backend(client, base, *, pause=time.sleep):
    first = client.post(base.rstrip('/') + '/api/v1/system/cache/invalidate')
    require(first.get('invalidated') is True and first.get('commit') == client.context['source_sha']
            and marker_valid(first.get('marker_identity')), 'backend invalidation refused')
    target, marker = census_key(first.get('census')), first['marker_identity']
    require(type(first.get('pid')) is int and first.get('pid') == int(first['census']['worker'].split(':')[0]), 'backend PID refused')
    seen = set()
    # Even a single worker must corroborate the marker after the original call.
    for _ in range(MAX_REQUESTS - 1):
        status = client.post(base.rstrip('/') + '/api/v1/system/cache/status')
        require(census_key(status.get('census')) == target, 'serving census changed')
        require(status.get('commit') == client.context['source_sha'] and status.get('synchronised') is True
                and marker_valid(status.get('observed_identity')) and marker_valid(status.get('adopted_identity'))
                and status['observed_identity'] == marker and status['adopted_identity'] == marker
                and type(status.get('pid')) is int and status.get('pid') == int(status['census']['worker'].split(':')[0]), 'worker adoption refused')
        seen.add(status['census']['worker'])
        if seen == set(target['workers']):
            return {'protocol': PROTOCOL, 'context': client.context, 'census': target,
                    'marker_identity': marker, 'adopted_workers': sorted(seen), 'at': int(client.now())}
        pause(min(.25, client.remaining()))
    raise ValueError('missing serving worker acknowledgments')


def revalidate_pages(client, state, url, paths):
    require(type(state) is dict and set(state) == {'protocol', 'context', 'census', 'marker_identity', 'adopted_workers', 'at'}
            and state['protocol'] == PROTOCOL and state['context'] == client.context
            and type(state['at']) is int and abs(client.now() - state['at']) <= 120
            and marker_valid(state['marker_identity']), 'backend adoption state refused')
    require(type(state['census']) is dict, 'backend census absent')
    original = dict(state['census'], worker=next(iter(state.get('adopted_workers', [])), None))
    require(census_key(original) == state['census'] and state['adopted_workers'] == state['census']['workers'],
            'backend adoption incomplete')
    require(type(paths) is list and 1 <= len(paths) <= 64 and all(type(p) is str and p.startswith('/') and len(p) <= 256 for p in paths)
            and len(set(paths)) == len(paths), 'page inventory refused')
    digest = hashlib.sha256(json.dumps(state, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    result = client.post(url, paths=paths, backend_adoption_sha256=digest)
    require(result.get('backend_adoption_sha256') == digest and result.get('rejected') == []
            and type(result.get('revalidated')) is list and len(result['revalidated']) == len(paths)
            and all(type(p) is str for p in result['revalidated'])
            and sorted(result['revalidated']) == sorted(paths), 'exact page acknowledgment refused')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('backend', 'pages'))
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    try:
        directory = Path(os.environ.get('RUNNER_TEMP', '/tmp')).resolve(strict=True)
        require(args.state.is_absolute() and args.evidence.is_absolute()
                and args.state.parent == directory and args.evidence.parent == directory
                and args.state != args.evidence, 'owned runtime artifact directory required')
        require(not args.state.is_symlink() and not args.evidence.is_symlink(), 'linked refresh artifact refused')
        needs = load(os.environ['REFRESH_NEEDS'])
        context = {'source_sha': os.environ['GITHUB_SHA'], 'plan_sha256': needs['source_plan']['outputs']['plan_sha256'],
                   'run_id': os.environ['GITHUB_RUN_ID'], 'run_attempt': os.environ['GITHUB_RUN_ATTEMPT'],
                   'schema_head': needs['migrate']['outputs']['schema_head']}
        client = SignedClient(os.environ['REVALIDATE_SECRET'], context, args.evidence)
        if args.phase == 'backend':
            require(not args.state.exists() and not args.evidence.exists(), 'fresh refresh artifact required')
            fd = private_evidence_fd(args.evidence, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
            os.close(fd)
            state = adopt_backend(client, os.environ['API_BASE_URL'])
            with args.state.open('x') as stream:
                state_raw = json.dumps(state, sort_keys=True, separators=(',', ':'))
                json.dump({'state': state, 'signature': hmac.new(client.secret.encode(), state_raw.encode(), hashlib.sha256).hexdigest()}, stream, separators=(',', ':'))
            require(load(args.state.read_bytes())['state'] == state, 'backend state disk readback refused')
        else:
            envelope = load(args.state.read_bytes())
            require(type(envelope) is dict and set(envelope) == {'state', 'signature'}
                    and type(envelope['signature']) is str, 'backend state envelope refused')
            state = envelope['state']
            expected = hmac.new(client.secret.encode(), json.dumps(state, sort_keys=True, separators=(',', ':')).encode(), hashlib.sha256).hexdigest()
            require(hmac.compare_digest(envelope['signature'], expected), 'backend state signature refused')
            paths = load(Path('frontend/lib/revalidation/paths.json').read_bytes())['paths']
            revalidate_pages(client, state, os.environ['REVALIDATE_URL'], paths)
        with os.fdopen(private_evidence_fd(args.evidence, os.O_RDONLY), 'rb') as evidence:
            originals = evidence.read(8_000_001)
            require(len(originals) <= 8_000_000, 'private evidence exceeds bound')
            evidence_sha256 = hashlib.sha256(originals).hexdigest()
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            stream.write('acknowledged=true\nprotocol=' + PROTOCOL + '\n')
            for key in ('source_sha', 'plan_sha256', 'run_id', 'run_attempt'):
                stream.write(key + '=' + context[key] + '\n')
            stream.write('evidence_sha256=' + evidence_sha256 + '\n')
        print(args.phase + ' signed acknowledgment verified')
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print('Refresh refused: ' + type(exc).__name__ + ': ' + str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
