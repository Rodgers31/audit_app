"""Offline import of the nightly producer's encrypted, signed HTTP transcript."""
import base64
import binascii
from datetime import datetime
import hashlib
import hmac
from ipaddress import ip_address
import re
import time
from urllib.parse import urlsplit

from common import Refusal, canonical, digest, fields, integer, loads, require
from acceptance_refresh import PATHS, invalidation_response
from operational import read_artifact

PROTOCOL = 'nightly-refresh-v2'
SEALED_SCHEMA = 'nightly-refresh-sealed-evidence-v1'
PREFIX = b'REFRESH_HTTP_EVIDENCE_V2 '
KEY_DOMAIN = b'auditgava:nightly-refresh-evidence:v1'
MAX_PRIVATE = 8_000_000
MAX_LINE = 196_608
MAX_BACKEND_REQUESTS = 64
INVALIDATE = '/api/v1/system/cache/invalidate'
STATUS = '/api/v1/system/cache/status'
CONTEXT = ('source_sha', 'plan_sha256', 'run_id', 'run_attempt', 'schema_head')


def load_refresh_json(raw):
    try:
        return loads(raw.decode('utf-8'))
    except (ValueError, RecursionError):
        # Decoder diagnostics can contain bytes from an original.
        raise Refusal('invalid refresh v2 JSON') from None


def _hex_hmac(key, raw):
    return hmac.digest(key, raw, 'sha256').hex()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _b64(value, maximum):
    require(type(value) is str and 0 < len(value) <= ((maximum + 2) // 3) * 4,
            'refresh base64 byte ceiling or type')
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise Refusal('invalid refresh base64') from None
    require(0 < len(raw) <= maximum and base64.b64encode(raw).decode('ascii') == value,
            'noncanonical refresh base64')
    return raw


def _open(line, key, used_ivs):
    from cryptography.exceptions import InvalidTag

    require(line.startswith(PREFIX) and len(line) <= MAX_LINE, 'sealed refresh record framing differs')
    sealed = load_refresh_json(line[len(PREFIX):])
    fields(sealed, ('schema', 'algorithm', 'nonce', 'ciphertext', 'tag', 'plaintext_sha256'))
    require(sealed['schema'] == SEALED_SCHEMA and sealed['algorithm'] == 'aes-256-gcm',
            'sealed refresh schema or algorithm differs')
    nonce, tag = _b64(sealed['nonce'], 12), _b64(sealed['tag'], 16)
    require(len(nonce) == 12 and len(tag) == 16 and nonce not in used_ivs,
            'invalid or repeated AES-GCM nonce/tag')
    used_ivs.add(nonce)
    ciphertext = _b64(sealed['ciphertext'], 131_072)
    try:
        raw = key.decrypt(nonce, ciphertext + tag, SEALED_SCHEMA.encode('ascii'))
    except InvalidTag:
        raise Refusal('sealed refresh authentication failed') from None
    require(hmac.compare_digest(digest(sealed['plaintext_sha256']), _sha(raw)),
            'sealed refresh plaintext digest differs')
    return raw


def _wire_context(value):
    fields(value, CONTEXT)
    digest(value['source_sha'], 40)
    digest(value['plan_sha256'])
    for field, pattern in (('run_id', '[1-9][0-9]{0,17}'), ('run_attempt', '[1-9][0-9]{0,4}')):
        require(type(value[field]) is str and re.fullmatch(pattern, value[field]) is not None,
                'invalid refresh v2 run identity')
    require(value['schema_head'] == 'a756b20a0001', 'invalid refresh v2 schema head')


def _process(value):
    require(type(value) is str and re.fullmatch('[1-9][0-9]{0,9}:[1-9][0-9]{0,19}', value),
            'invalid kernel PID/start ticks')
    return int(value.split(':', 1)[0])


def _kernel(snapshot):
    fields(snapshot, ('boot_id', 'pid_namespace_inode', 'supervisor', 'workers', 'listeners'))
    boot, supervisor, workers = snapshot['boot_id'], snapshot['supervisor'], snapshot['workers']
    require(type(boot) is str and re.fullmatch('[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot),
            'actual Linux boot identity required')
    namespace = integer(snapshot['pid_namespace_inode'], 1)
    supervisor_pid = _process(supervisor)
    require(type(workers) is list and 1 <= len(workers) < MAX_BACKEND_REQUESTS,
            'serving worker inventory exceeds backend request budget')
    pids = {_process(worker) for worker in workers}
    require(len(pids) == len(workers) and workers == sorted(workers)
            and (supervisor_pid not in pids or (supervisor_pid == 1 and workers == [supervisor])),
            'inconsistent kernel supervisor or worker identities')
    listeners = snapshot['listeners']
    require(type(listeners) is list and 1 <= len(listeners) <= 128, 'kernel listener inventory required')
    seen_inodes, seen_holders = set(), set()
    allowed = {supervisor, *workers}
    for listener in listeners:
        fields(listener, ('port', 'inode', 'holders'))
        require(integer(listener['port'], 1) <= 65535, 'invalid kernel listener port')
        inode = integer(listener['inode'], 1)
        require(inode not in seen_inodes, 'duplicate kernel listener')
        seen_inodes.add(inode)
        holders = listener['holders']
        require(type(holders) is list and 1 <= len(holders) <= len(allowed)
                and all(type(holder) is str and holder in allowed for holder in holders)
                and holders == sorted(set(holders)),
                'unaccounted kernel listener holder')
        seen_holders.update(holders)
    require(seen_holders == allowed, 'kernel listeners omit a serving supervisor or worker')
    return {'scope': 'container', 'instance': _sha(f'{boot}:{namespace}:{supervisor}'.encode('ascii')),
            'supervisor': supervisor, 'workers': workers}


def _https(value):
    require(type(value) is str and value.isascii() and 0 < len(value) <= 2048
            and all(32 < ord(char) < 127 for char in value) and not any(char in value for char in '\\?#'),
            'invalid refresh HTTPS target')
    try:
        parsed = urlsplit(value)
        valid = (value.startswith('https://') and parsed.hostname and parsed.username is None
                 and parsed.password is None and parsed.port != 0)
    except ValueError:
        valid = False
    require(valid, 'invalid refresh HTTPS target')
    return parsed


def _marker(value):
    require(type(value) is list and len(value) == 3 and all(type(n) is int and n > 0 for n in value)
            and value[2] == 32, 'invalid backend generation marker identity')
    return value


def _witness(value, expected_context, manifest_sha, not_before):
    fields(value, ('schema', 'context', 'started_at', 'finished_at', 'backend_origin', 'frontend',
                   'backend_before', 'backend_after', 'generation', 'marker_identity',
                   'backend_exit', 'pages_exit'))
    require(value['schema'] == 'nightly-refresh-local-witness-v2', 'unknown independent refresh witness')
    _wire_context(value['context'])
    require(value['context'] == expected_context, 'independent witness context differs')
    start, end = integer(value['started_at'], 1), integer(value['finished_at'], 1)
    require(not_before <= start <= end and end - start <= 300
            and 0 <= int(time.time()) - end <= 604_800, 'stale/future/over-budget refresh witness')
    require(integer(value['backend_exit']) == integer(value['pages_exit']) == 0,
            'both original refresh child exits must be zero')
    backend = value['backend_origin']
    origin = _https(backend)
    require(origin.path == '', 'backend refresh origin must have no path')
    front = value['frontend']
    fields(front, ('url', 'commit', 'manifest_sha256'))
    require(_https(front['url']).path not in ('', '/') and front['url'] not in (backend + INVALIDATE, backend + STATUS)
            and digest(front['commit'], 40) == expected_context['source_sha']
            and digest(front['manifest_sha256']) == manifest_sha, 'independent frontend identity differs')
    target = _kernel(value['backend_before'])
    require(_kernel(value['backend_after']) == target
            and value['backend_before'] == value['backend_after'], 'kernel serving census changed')
    try:
        loopback = ip_address(origin.hostname).is_loopback
    except ValueError:
        loopback = origin.hostname == 'localhost'
    if loopback:
        require((origin.port or 443) in {item['port'] for item in value['backend_before']['listeners']},
                'loopback origin port differs from the observed listener')
    digest(value['generation'], 32)
    _marker(value['marker_identity'])
    return target


def _phase_output(raw, context, checksum):
    expected = {'acknowledged': 'true', 'protocol': PROTOCOL,
                **{key: context[key] for key in CONTEXT if key != 'schema_head'},
                'evidence_sha256': checksum}
    require(raw == ''.join(f'{key}={value}\n' for key, value in expected.items()).encode('ascii'),
            'refresh phase output or exact original transcript digest differs')


def _exchange(raw, key, context, url, previous_ts, end, nonces, *, pages):
    record = load_refresh_json(raw)
    fields(record, ('request_base64', 'response_base64', 'request_sha256', 'response_sha256',
                    'request_signature', 'response_signature', 'url', 'http_status'))
    require(record['url'] == url and integer(record['http_status']) == 200,
            'unexpected refresh URL/order or HTTP status')
    request_raw = _b64(record['request_base64'], 8192)
    response_raw = _b64(record['response_base64'], 65536)
    for kind, message in (('request', request_raw), ('response', response_raw)):
        require(hmac.compare_digest(digest(record[kind + '_sha256']), _sha(message)),
                f'original refresh {kind} digest differs')
        require(hmac.compare_digest(digest(record[kind + '_signature']), _hex_hmac(key, message)),
                f'original refresh {kind} HMAC differs')
    request, response = load_refresh_json(request_raw), load_refresh_json(response_raw)
    request_fields = ('protocol', 'ts', 'nonce', 'context')
    fields(request, (*request_fields, 'paths', 'backend_adoption_sha256') if pages else request_fields)
    fields(response, ('protocol', 'context', 'request_sha256', 'at', 'result'))
    for value in (request, response):
        _wire_context(value['context'])
        require(value['protocol'] == PROTOCOL and value['context'] == context,
                'original refresh v2 protocol or context differs')
    nonce = digest(request['nonce'], 32)
    require(nonce not in nonces, 'duplicate or replayed HTTP request nonce')
    nonces.add(nonce)
    ts, at = integer(request['ts'], 1), integer(response['at'], 1)
    require(previous_ts <= ts <= end and abs(at - ts) <= 300 and at <= int(time.time()) + 300,
            'stale/future/reordered HTTP receipt')
    require(digest(response['request_sha256']) == _sha(request_raw), 'response is for another request')
    return request, response


def _worker(result, expected_census, commit):
    census = result['census']
    fields(census, (*expected_census, 'worker'))
    require({k: census[k] for k in expected_census} == expected_census
            and census['worker'] in expected_census['workers']
            and integer(result['pid'], 1) == _process(census['worker'])
            and result['commit'] == commit, 'signed serving census, PID or commit differs')
    return census['worker']


def _iso(value, expected, *, elapsed_seconds=1):
    require(type(value) is str and 1 <= len(value) <= 40, 'invalid acknowledgment time')
    try:
        at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise Refusal('invalid acknowledgment time') from None
    require(at.utcoffset() is not None and at.utcoffset().total_seconds() == 0
            and -1 <= expected - at.timestamp() <= elapsed_seconds, 'signed acknowledgment time differs')


def _invalidation(result, context, target, witness, at):
    fields(result, ('invalidated', 'reason', 'at', 'redis', 'local', 'generation',
                    'marker_identity', 'pid', 'census', 'commit'))
    _worker(result, target, context['source_sha'])
    fields(result['local'], ('cleared_entries', 'by_cache'))
    require(result['reason'] is None, 'nightly invalidation reason differs')
    _iso(result['at'], at, elapsed_seconds=6)
    marker = invalidation_response(result, {result['pid']}, None)
    require(result['redis']['configured'] or result['redis']['deleted'] == 0,
            'inconsistent Redis invalidation counts')
    require('redis_cache_memory' in result['local']['by_cache'], 'missing in-process Redis cache observation')
    require(_marker(marker) == witness['marker_identity']
            and result['generation'] == witness['generation'], 'backend generation or marker differs from witness')
    return marker


def _adoption(raw, key, context, target, marker, first_ts, last_ts, page_ts):
    envelope = load_refresh_json(raw)
    fields(envelope, ('state', 'signature'))
    state = envelope['state']
    fields(state, ('protocol', 'context', 'census', 'marker_identity', 'adopted_workers', 'at'))
    _wire_context(state['context'])
    at = integer(state['at'], 1)
    require(at - first_ts <= 90, 'backend adoption exceeded original phase budget')
    require(state['protocol'] == PROTOCOL and state['context'] == context and state['census'] == target
            and _marker(state['marker_identity']) == marker and state['adopted_workers'] == target['workers']
            and last_ts <= at <= page_ts and page_ts - at <= 120,
            'original backend adoption state differs or is stale')
    raw_state = canonical(state)
    require(hmac.compare_digest(digest(envelope['signature']), _hex_hmac(key, raw_state)),
            'backend adoption state HMAC differs')
    return _sha(raw_state)


def verify_v2(*, originals, root, bundle, witness, secret, expected_context, not_before):
    """Verify producer bytes against independently obtained local observations."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    require(type(secret) is bytes and 0 < len(secret) <= 65536 and b'\0' not in secret,
            'bounded v2 signing key bytes required')
    try:
        secret.decode('utf-8')
    except UnicodeError:
        raise Refusal('v2 signing key must be exact UTF-8 bytes') from None
    _wire_context(expected_context)
    integer(not_before, 1)
    fields(bundle, ('schema', 'sealed', 'state', 'backend_output', 'pages_output'))
    require(bundle['schema'] == 'nightly-refresh-v2-bundle-v1', 'unknown v2 bundle schema')

    def read(name, limit):
        return read_artifact(bundle[name], root, originals, private=True, maximum_bytes=limit)

    manifest = originals.read(PATHS, maximum_bytes=16384)
    manifest_value = load_refresh_json(manifest)
    fields(manifest_value, ('$comment', 'paths'))
    paths = manifest_value['paths']
    require(type(paths) is list and 1 <= len(paths) <= 64
            and all(type(p) is str and p.startswith('/') and len(p) <= 256 for p in paths)
            and len(set(paths)) == len(paths), 'exact source frontend manifest unavailable')
    target = _witness(witness, expected_context, _sha(manifest), not_before)
    sealed = read('sealed', MAX_LINE * (MAX_BACKEND_REQUESTS + 1))
    require(sealed.endswith(b'\n'), 'incomplete sealed refresh transcript')
    lines = sealed[:-1].split(b'\n', MAX_BACKEND_REQUESTS + 1)
    require(3 <= len(lines) <= MAX_BACKEND_REQUESTS + 1, 'incomplete or excessive signed refresh inventory')

    archive_key = AESGCM(hmac.digest(secret, KEY_DOMAIN, 'sha256'))
    used_ivs, nonces, adopted = set(), set(), set()
    transcript, transcript_size = hashlib.sha256(), 0
    previous_ts = witness['started_at']
    backend = witness['backend_origin']
    workers = set(target['workers'])
    for index, line in enumerate(lines):
        pages = index == len(lines) - 1
        url = witness['frontend']['url'] if pages else backend + (INVALIDATE if index == 0 else STATUS)
        raw = _open(line, archive_key, used_ivs)
        request, response = _exchange(raw, secret, expected_context, url, previous_ts,
                                      witness['finished_at'], nonces, pages=pages)
        result = response['result']
        if index == 0:
            first_ts = request['ts']
            marker = _invalidation(result, expected_context, target, witness, response['at'])
        elif pages:
            require(adopted == workers, 'frontend acknowledgment precedes full worker adoption')
            _phase_output(read('backend_output', 1024), expected_context, transcript.hexdigest())
            adoption = _adoption(read('state', 16384), secret, expected_context,
                                 target, marker, first_ts, previous_ts, request['ts'])
            require(witness['finished_at'] - request['ts'] <= 90, 'frontend acknowledgment exceeded original phase budget')
            fields(result, ('revalidated', 'rejected', 'at', 'backend_adoption_sha256'))
            require(request['paths'] == paths and result['revalidated'] == paths and result['rejected'] == []
                    and digest(request['backend_adoption_sha256']) == adoption
                    and digest(result['backend_adoption_sha256']) == adoption,
                    'frontend adoption digest or exact manifest acknowledgment differs')
            _iso(result['at'], response['at'])
        else:
            require(adopted != workers and request['ts'] - first_ts <= 90,
                    'extra or over-budget backend status receipts')
            fields(result, ('pid', 'commit', 'marker_path', 'observed_identity',
                            'adopted_identity', 'synchronised', 'census'))
            worker = _worker(result, target, expected_context['source_sha'])
            require(result['synchronised'] is True and _marker(result['observed_identity']) == marker
                    and _marker(result['adopted_identity']) == marker
                    and type(result['marker_path']) is str and 0 < len(result['marker_path']) <= 4096,
                    'worker did not adopt original generation')
            adopted.add(worker)
        previous_ts = request['ts']
        transcript_size += len(raw) + 1
        require(transcript_size <= MAX_PRIVATE, 'original refresh transcript byte ceiling')
        transcript.update(raw)
        transcript.update(b'\n')
    _phase_output(read('pages_output', 1024), expected_context, transcript.hexdigest())
    return {'protocol': PROTOCOL, 'verdict': 'OFFLINE_V2_HTTP_HMAC_AND_ACK_SEMANTICS_VERIFIED',
            'context': expected_context, 'worker_count': len(workers), 'paths': paths,
            'backend_adoption_sha256': adoption, 'original_http_evidence_sha256': transcript.hexdigest(),
            'evidence_verified': True, 'cache_acknowledged': True, 'production_accepted': False}
