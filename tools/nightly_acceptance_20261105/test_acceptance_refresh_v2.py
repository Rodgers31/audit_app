"""Node-produced ciphertext and exact wire adversaries for the offline importer."""
from base64 import b64encode
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import subprocess
import time

import pytest

from acceptance_refresh import PATHS, ROOT
from acceptance_refresh_v2 import PREFIX, PROTOCOL, verify_v2
from common import BoundEvidence, Refusal, canonical
from operational import observe_local


PRODUCER = ROOT / 'scripts/verification/nightly_workflow/evidence.cjs'
BACKEND = 'https://backend.invalid'
FRONTEND = 'https://frontend.invalid/api/revalidate'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def signature(secret, raw):
    return hmac.digest(secret, raw, 'sha256').hex()


def private(path, raw):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
        stream.write(raw)
    return {'path': path.name, 'sha256': sha(raw), 'size': len(raw)}


def output(context, transcript):
    return ('acknowledged=true\nprotocol=' + PROTOCOL + '\n' +
            ''.join(f'{key}={context[key]}\n' for key in ('source_sha', 'plan_sha256', 'run_id', 'run_attempt')) +
            'evidence_sha256=' + sha(transcript) + '\n').encode()


def seal(records, secret):
    # Batch independent envelopes through the genuine producer implementation.
    script = """
        const fs = require('node:fs');
        const {seal} = require(process.argv[1]);
        const lines = fs.readFileSync(0, 'utf8').trimEnd().split('\\n');
        for (const line of lines) {
            const value = seal(Buffer.from(line), process.env.REVALIDATE_SECRET);
            process.stdout.write('REFRESH_HTTP_EVIDENCE_V2 ' + JSON.stringify(value) + '\\n');
        }
    """
    return subprocess.run(['node', '-e', script, str(PRODUCER)], input=b''.join(raw + b'\n' for raw in records),
                          env={'PATH': os.environ['PATH'], 'REVALIDATE_SECRET': secret.decode('utf-8')},
                          check=True, capture_output=True, timeout=15).stdout


@pytest.fixture
def trace():
    secret = b'inert-v2-wire-corpus'
    now = int(time.time()) - 20
    iso = datetime.fromtimestamp(now, timezone.utc).isoformat()
    manifest = PATHS.read_bytes()
    paths = json.loads(manifest)['paths']
    context = dict(source_sha='a'*40, plan_sha256='b'*64, run_id='97531', run_attempt='1', schema_head='a756b20a0001')
    snapshot = dict(boot_id='00000000-0000-0000-0000-000000000123', pid_namespace_inode=505,
                    supervisor='4:5', workers=['8:9', '9:10'],
                    listeners=[dict(port=8090, inode=151, holders=['4:5', '8:9', '9:10'])])
    target = dict(scope='container', instance=sha(b'00000000-0000-0000-0000-000000000123:505:4:5'),
                  supervisor='4:5', workers=['8:9', '9:10'])
    marker, generation = [442, 123456789, 32], 'a1'*16
    witness = dict(schema='nightly-refresh-local-witness-v2', context=dict(context),
                   started_at=now-1, finished_at=now+2, backend_origin=BACKEND,
                   frontend=dict(url=FRONTEND, commit=context['source_sha'], manifest_sha256=sha(manifest)),
                   backend_before=snapshot, backend_after=json.loads(canonical(snapshot)),
                   marker_identity=marker, generation=generation, backend_exit=0, pages_exit=0)
    state = dict(protocol=PROTOCOL, context=dict(context), census=target,
                 marker_identity=marker, adopted_workers=target['workers'], at=now)
    adoption = sha(canonical(state))
    requests = [dict(protocol=PROTOCOL, ts=now, context=dict(context), nonce=f'{i:032x}') for i in range(1, 6)]
    requests[-1].update(paths=paths, backend_adoption_sha256=adoption)

    def status(worker):
        return dict(pid=int(worker.split(':')[0]), census=dict(target, worker=worker), commit=context['source_sha'],
                    marker_path='/fixture/generation', observed_identity=marker, adopted_identity=marker, synchronised=True)

    invalidated = dict(pid=8, census=dict(target, worker='8:9'), commit=context['source_sha'],
                       invalidated=True, reason=None, at=iso,
                       marker_identity=marker, generation=generation,
                       redis=dict(configured=False, deleted=0), local=dict(cleared_entries=0, by_cache={'redis_cache_memory': 0, 'owned': 0}))
    # The producer legitimately repeats a status poll with fresh nonces before full coverage.
    results = [invalidated, status('8:9'), status('8:9'), status('9:10'),
               dict(revalidated=paths, rejected=[], at=iso, backend_adoption_sha256=adoption)]
    responses = [dict(protocol=PROTOCOL, context=dict(context), at=now, result=r) for r in results]
    return dict(context=context, state=state, witness=witness, requests=requests, responses=responses,
                secret=secret, now=now)


def save(root, trace, fault=None):
    requests, responses = trace['requests'], trace['responses']
    context, secret, state = (trace[key] for key in ('context', 'secret', 'state'))
    invalidate = BACKEND + '/api/v1/system/cache/invalidate'
    status = BACKEND + '/api/v1/system/cache/status'
    urls = [invalidate, status, status, status, FRONTEND]
    records = []
    for request, response, url in zip(requests, responses, urls, strict=True):
        req = json.dumps(request).encode()
        response['request_sha256'] = sha(req)
        if fault == 'misbound-response' and url == FRONTEND:
            response['request_sha256'] = 'b'*64
        ack = json.dumps(response).encode()
        records.append(dict(request_base64=b64encode(req).decode(), response_base64=b64encode(ack).decode(),
                            request_sha256=sha(req), response_sha256=sha(ack), request_signature=signature(secret, req),
                            response_signature=signature(secret, ack), url=url, http_status=200))
    if fault in ('request_signature', 'response_signature', 'response_sha256'):
        records[-1][fault] = '1'*64
    if fault == 'reordered':
        records[-1], records[-2] = records[-2], records[-1]
    if fault == 'failed-status':
        records[-1]['http_status'] = 502
    if fault == 'truncated':
        records.pop(3)
    if fault == 'extra-status':
        repeated = dict(records[2])
        records.insert(-1, repeated)
    raw = [json.dumps(row, separators=(',', ':')).encode() for row in records]
    sealed = seal(raw, secret)
    if fault in ('tag', 'plaintext_sha256'):
        lines = sealed.splitlines()
        frame = json.loads(lines[-1][len(PREFIX):])
        frame[fault] = ('1'*64 if fault == 'plaintext_sha256' else b64encode(bytes(16)).decode())
        lines[-1] = PREFIX + canonical(frame)
        sealed = b'\n'.join(lines) + b'\n'
    if fault == 'duplicate-envelope':
        lines = sealed.splitlines(keepends=True)
        sealed = b''.join([*lines[:-1], lines[1], lines[-1]])
    return dict(schema='nightly-refresh-v2-bundle-v1',
                sealed=private(root/'sealed.log', sealed),
                state=private(root/'state.json', canonical(dict(state=state, signature=
                    '1'*64 if fault == 'state-hmac' else signature(secret, canonical(state))))),
                backend_output=private(root/'backend.out', output(context, b''.join(item+b'\n' for item in raw[:-1]))),
                pages_output=private(root/'pages.out', output(context, b'wrong' if fault == 'partial-output' else
                                                              b''.join(item+b'\n' for item in raw))))


def verify(root, trace, bundle, *, key=None):
    with BoundEvidence() as originals:
        return verify_v2(originals=originals, root=root, bundle=bundle, witness=trace['witness'],
                         secret=trace['secret'] if key is None else key,
                         expected_context=trace['context'], not_before=trace['now']-10)


def test_node_envelopes_preserve_issuer_signed_bytes_and_distinct_poll_nonces(tmp_path, trace):
    root = tmp_path.resolve()
    # Inner timestamp precedes the signed envelope clock while the second kernel census runs.
    trace['responses'][0]['at'] += 2
    result = verify(root, trace, save(root, trace))
    assert result['worker_count'] == 2
    assert result['cache_acknowledged'] is result['evidence_verified'] is True
    assert result['production_accepted'] is False


@pytest.mark.parametrize(('fault', 'reason'), [
    ('tag', 'authentication failed'), ('plaintext_sha256', 'plaintext digest'),
    ('request_signature', 'request HMAC'), ('response_signature', 'response HMAC'),
    ('response_sha256', 'response digest'), ('wrong-key', 'authentication failed'),
    ('misbound-response', 'another request'), ('duplicate-envelope', 'repeated AES-GCM'),
    ('reordered', 'URL/order'), ('failed-status', 'HTTP status'), ('truncated', 'full worker'),
    ('extra-status', 'replayed HTTP'), ('partial-output', 'phase output'),
    ('state-hmac', 'state HMAC'), ('bad-nonce', '32-character'), ('replay', 'replayed HTTP'),
    ('schema', 'schema head'), ('wrong-run', 'context differs'), ('wrong-plan', 'context differs'),
    ('legacy', 'protocol or context'), ('float-time', 'integer'), ('stale', 'stale/future'),
    ('false-invalidation', 'no actual generation'), ('false-adoption', 'did not adopt'),
    ('wrong-marker', 'did not adopt'), ('wrong-generation', 'generation or marker'),
    ('wrong-worker', 'census, PID'), ('wrong-serving-commit', 'census, PID'),
    ('pages-missing', 'manifest acknowledgment'), ('page-duplicate', 'manifest acknowledgment'),
    ('wrong-adoption', 'manifest acknowledgment'), ('wrong-page-commit', 'frontend identity'),
    ('stale-witness', 'witness'), ('churned-census', 'census changed'),
    ('missing-supervisor-holder', 'omit a serving supervisor'), ('nonzero-exit', 'exits'),
    ('contradictory-redis', 'inconsistent Redis'), ('missing-memory', 'missing in-process'),
    ('late-backend-state', 'backend adoption exceeded'), ('late-page-completion', 'frontend acknowledgment exceeded'),
    ('wrong-loopback-port', 'origin port differs'), ('bool-exit', 'integer'), ('wrong-witness-digest', 'frontend identity'),
    ('public-original', 'private owned original'), ('alias-original', 'hardlink alias'),
])
def test_refresh_v2_refuses_hostile_recatalogued_originals(tmp_path, trace, fault, reason):
    root = tmp_path.resolve()
    requests, responses, witness = (trace[key] for key in ('requests', 'responses', 'witness'))
    if fault == 'bad-nonce': requests[-1]['nonce'] = 1
    if fault == 'replay': requests[-1]['nonce'] = requests[0]['nonce']
    if fault == 'schema': requests[-1]['context']['schema_head'] = 'old'
    if fault == 'wrong-run': requests[-1]['context']['run_attempt'] = '2'
    if fault == 'wrong-plan': responses[-1]['context']['plan_sha256'] = '9'*64
    if fault == 'legacy': requests[-1]['protocol'] = 'nightly-refresh-capture-v1'
    if fault == 'float-time': requests[-1]['ts'] = float(trace['now'])
    if fault == 'stale': responses[-1]['at'] -= 301
    if fault == 'false-invalidation': responses[0]['result']['invalidated'] = 1
    if fault == 'false-adoption': responses[2]['result']['synchronised'] = 1
    if fault == 'wrong-marker': responses[2]['result']['adopted_identity'] = [7, 8, 32]
    if fault == 'wrong-generation': responses[0]['result']['generation'] = 'd'*32
    if fault == 'wrong-worker': responses[2]['result']['census']['worker'] = '9:10'
    if fault == 'wrong-serving-commit': responses[2]['result']['commit'] = 'c'*40
    if fault == 'pages-missing': responses[-1]['result']['revalidated'] = ['/']
    if fault == 'page-duplicate': requests[-1]['paths'] = ['/', '/']
    if fault == 'wrong-adoption': responses[-1]['result']['backend_adoption_sha256'] = 'd'*64
    if fault == 'wrong-page-commit': witness['frontend']['commit'] = 'd'*40
    if fault == 'stale-witness': witness['finished_at'] -= 604801
    if fault == 'churned-census': witness['backend_after']['listeners'][0]['inode'] += 1
    if fault == 'missing-supervisor-holder':
        for boundary in ('backend_before', 'backend_after'):
            witness[boundary]['listeners'][0]['holders'].remove('4:5')
    if fault == 'nonzero-exit': witness['pages_exit'] = 1
    if fault == 'contradictory-redis': responses[0]['result']['redis']['deleted'] = 8
    if fault == 'missing-memory': del responses[0]['result']['local']['by_cache']['redis_cache_memory']
    if fault == 'late-backend-state':
        witness['started_at'] -= 100
        trace['now'] -= 100
        for request, response in zip(requests[:-1], responses[:-1], strict=True):
            request['ts'] -= 100
            response['at'] -= 100
        responses[0]['result']['at'] = datetime.fromtimestamp(responses[0]['at'], timezone.utc).isoformat()
    if fault == 'late-page-completion':
        witness['started_at'] -= 100
        trace['now'] -= 100
        for request, response in zip(requests, responses, strict=True):
            request['ts'] -= 100
            response['at'] -= 100
            if 'at' in response['result']:
                response['result']['at'] = datetime.fromtimestamp(response['at'], timezone.utc).isoformat()
        trace['state']['at'] -= 100
        adoption = sha(canonical(trace['state']))
        requests[-1]['backend_adoption_sha256'] = responses[-1]['result']['backend_adoption_sha256'] = adoption
    if fault == 'wrong-loopback-port': witness['backend_origin'] = 'https://127.0.0.1:65534'
    if fault == 'bool-exit': witness['pages_exit'] = False
    if fault == 'wrong-witness-digest': witness['frontend']['manifest_sha256'] = 'd'*64
    bundle = save(root, trace, fault)
    if fault == 'public-original': (root/'sealed.log').chmod(0o644)
    if fault == 'alias-original': os.link(root/'sealed.log', root/'alias')
    with pytest.raises(Refusal, match=reason):
        verify(root, trace, bundle, key=b'another-inert-key' if fault == 'wrong-key' else None)


def test_v2_expectation_refuses_legacy_before_opening_a_database(tmp_path):
    root = tmp_path.resolve()
    config = dict(schema='nightly-backend-config-v1', plugins=['pytest_asyncio.plugin', 'acceptance_backend'],
                  pg_url='postgresql+psycopg2://postgres@127.0.0.1:55432/auditgava_refresh_fixture',
                  fixture_token='0'*32, original_family='none')
    packet = dict.fromkeys(('kind', 'binding', 'plan', 'context', 'current_report', 'pg_schema',
                           'refresh', 'census', 'oag', 'fiscal'))
    packet['schema'] = 'nightly-semantic-local-input-v1'
    private(root/'config', canonical(config))
    private(root/'input', canonical(packet))
    with pytest.raises(Refusal, match='does not meet the requested version'):
        observe_local(root/'input', backend_config=root/'config', signing_key_file=root/'missing',
                      expected_refresh_protocol=PROTOCOL)


@pytest.mark.parametrize('malformed', ['census', 'refresh'])
def test_private_v2_json_errors_omit_original_fields(tmp_path, malformed):
    root = tmp_path.resolve()
    config = dict(schema='nightly-backend-config-v1', plugins=['pytest_asyncio.plugin', 'acceptance_backend'],
                  pg_url='postgresql+psycopg2://postgres@127.0.0.1:55432/auditgava_refresh_fixture',
                  fixture_token='0'*32, original_family='none')
    run = dict(commit='a'*40, run_id=10, attempt=1)
    key_name = 'private-fixture-field'
    invalid = ('{"' + key_name + '":1,"' + key_name + '":2}').encode()
    packet = dict(schema='nightly-semantic-local-input-v2', kind='full15', binding=run, pg_schema='unused',
                  plan=private(root/'plan', b'{}'), current_report=private(root/'report', b'{}'),
                  context=private(root/'context', canonical(dict(source_sha=run['commit'], run_id='10', run_attempt='1'))),
                  refresh=private(root/'refresh', invalid if malformed == 'refresh' else b'{}'),
                  census=private(root/'census', invalid if malformed == 'census' else b'{}'), oag=[], fiscal=None)
    private(root/'config', canonical(config))
    private(root/'key', b'inert-test-only')
    private(root/'input', canonical(packet))
    with pytest.raises(Refusal, match='^invalid refresh v2 JSON$') as refusal:
        observe_local(root/'input', backend_config=root/'config', signing_key_file=root/'key',
                      expected_refresh_protocol=PROTOCOL)
    assert key_name not in str(refusal.value)
