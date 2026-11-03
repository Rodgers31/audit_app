"""Bounded local observations with all operational controls held.

No network, SDK, database, worker or media-runtime composition. Image fixtures
exist only in a private temporary directory. Results do not authorize a launch.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
from urllib.parse import urlsplit

FLAGS = ('SOCIAL_MEDIA_ENABLED', 'SOCIAL_MEDIA_RETAINED_WRITES_ENABLED',
         'SOCIAL_MEDIA_FENCED_RETIREMENT_ENABLED', 'SOCIAL_MEDIA_OWNED_QUIESCENCE_ENABLED',
         'SOCIAL_WORKER_MEDIA_READS_ENABLED',
         'SOCIAL_NATIVE_ENABLED', 'SOCIAL_NATIVE_OPERATIONAL_GATES_VERIFIED',
         'SOCIAL_WORKER_SUPERVISOR_ENABLED', 'SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED',
         'SOCIAL_GENERATION_HOOK_ENABLED', 'SOCIAL_REPORT_GENERATION_ENABLED',
         'SOCIAL_POLICY_AUTOMATION_ENABLED', 'SOCIAL_STUDIO_ENABLED', 'SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED',
         'AUTO_SEEDER_ENABLED', 'ADMIN_ETL_DISPATCH_ENABLED')
CGROUP_FILES = ('memory.current', 'memory.max', 'memory.peak', 'memory.events',
                'cpu.max', 'cpu.stat', 'pids.current', 'pids.max')
DB_REFERENCES = ('DATABASE_URL', 'ADMIN_AUDIT_DATABASE_URL', 'SOCIAL_WORKER_DATABASE_URL')
MEDIA_FILES = ('inspection.py', 'inspection_child.py', 'config.py')


def require(value, message):
    if value is not True:
        raise ValueError(message)


def exact_integer(value, minimum=0, maximum=2**63-1):
    require(type(value) is int and minimum <= value <= maximum, 'Invalid bounded integer')
    return value


def counter(value):
    require(type(value) is str and re.fullmatch(r'0|[1-9][0-9]{0,19}', value) is not None,
            'Malformed host counter')
    return exact_integer(int(value))


def held_flags(values, expected_source):
    require(type(expected_source) is str and re.fullmatch('[a-f0-9]{40}', expected_source) is not None,
            'Exact source identity required')
    require(values.get('RENDER_GIT_COMMIT') == expected_source, 'Serving source changed')
    require(all(name not in values or type(values[name]) is str and values[name] == 'false'
                for name in FLAGS),
            'Enabled or malformed operational control')
    return {name: values[name] if name in values else '<unset>' for name in FLAGS}


def endpoint_metadata(value):
    if value is None:
        return {'present': False}
    require(type(value) is str and 0 < len(value) <= 8192, 'Malformed database reference')
    parsed = urlsplit(value)
    require(parsed.scheme in ('postgresql', 'postgresql+psycopg2') and bool(parsed.hostname),
            'Unsupported database reference')
    port = parsed.port if parsed.port is not None else 5432
    require(port in (5432, 6543), 'Unexpected database port')
    family = ('transaction_pooler' if parsed.hostname.endswith('.pooler.supabase.com') and port == 6543
              else 'session_pooler' if parsed.hostname.endswith('.pooler.supabase.com')
              else 'direct' if parsed.hostname.startswith('db.') and parsed.hostname.endswith('.supabase.co')
              else 'other')
    digest = lambda text: hashlib.sha256(text.encode()).hexdigest()
    return {'present': True, 'family': family, 'port': port,
            'endpoint_group_sha256': digest(f'{parsed.hostname}:{port}/{parsed.path}'),
            'login_sha256': digest(parsed.username or ''),
            'scope': 'Configured reference, not a connection or credential validation'}


def cgroup_snapshot(root=Path('/sys/fs/cgroup')):
    result = {}
    for name in CGROUP_FILES:
        path = root / name
        if not path.is_file():
            result[name] = {'available': False}
            continue
        raw = path.read_text()
        require(0 < len(raw) <= 4096, 'Host counter output bound')
        raw = raw.strip()
        if name in ('memory.events', 'cpu.stat'):
            pairs = [line.split() for line in raw.splitlines()]
            require(bool(pairs) and all(len(row) == 2 for row in pairs), 'Malformed host counter map')
            require(len({row[0] for row in pairs}) == len(pairs), 'Duplicate host counter')
            result[name] = {key: counter(value) for key, value in pairs}
        elif name == 'cpu.max':
            parts = raw.split()
            require(len(parts) == 2, 'Malformed CPU quota')
            quota = None if parts[0] == 'max' else counter(parts[0])
            period = counter(parts[1]); require(period > 0, 'Invalid CPU period')
            result[name] = {'quota_usec': quota, 'period_usec': period}
        else:
            result[name] = None if raw == 'max' else counter(raw)
    return result


def process_inventory(root=Path('/proc')):
    require(root.is_dir(), 'Linux process inventory required')
    result = []
    for path in sorted(root.iterdir(), key=lambda p: p.name):
        if not path.name.isdecimal():
            continue
        try:
            status = (path / 'status').read_text()
            comm = (path / 'comm').read_text().strip()
            args = (path / 'cmdline').read_bytes()
        except FileNotFoundError:
            continue
        require(len(status) <= 65536 and len(args) <= 131072, 'Process evidence bound')
        fields = dict(line.split(':', 1) for line in status.splitlines() if ':' in line)
        rss = fields.get('VmRSS')
        if rss is not None:
            rss = rss.strip().split()
            require(len(rss) == 2 and rss[1] == 'kB', 'Malformed process RSS')
        role = ('probe' if int(path.name) == os.getpid() else
                'web_master' if b'gunicorn: master' in args else
                'web_worker' if b'gunicorn: worker' in args else
                'web' if 'gunicorn' in comm else
                'shell' if comm in ('bash', 'sh') else 'other')
        result.append({'pid': int(path.name), 'role': role,
                       'rss_bytes': counter(rss[0])*1024 if rss is not None else None,
                       'threads': counter(fields['Threads'].strip())})
    require(bool(result) and len(result) <= 128, 'Incomplete or oversized process inventory')
    return result


def compile_product(path, name):
    """Compile measured source bytes; do not execute a cached Python file."""
    source = path.read_bytes()
    require(0 < len(source) <= 65536, 'Product source bound')
    module = type(sys)(name); module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(source, str(path), 'exec', dont_inherit=True), module.__dict__)
    return module


def read_packet(path):
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate fixture field')
            result[key] = value
        return result

    def reject_constant(_):
        raise ValueError('Nonfinite fixture constant')

    with path.open('rb') as stream:
        raw = stream.read(1048577)
    require(0 < len(raw) <= 1048576, 'Fixture packet byte bound')
    packet = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=reject_constant)
    require(type(packet) is dict and set(packet) == {'fixtures', 'product_sha256'},
            'Exact fixture packet shape')
    return packet


def inspect_images(media_root, fixtures, expected_hashes):
    require(type(fixtures) is list and len(fixtures) == 2, 'PNG and JPEG fixtures required')
    require(all(type(row) is dict for row in fixtures)
            and {row.get('mime') for row in fixtures} == {'image/png','image/jpeg'},
            'Distinct PNG and JPEG fixtures required')
    require(type(expected_hashes) is dict and set(expected_hashes) == set(MEDIA_FILES),
            'Exact measured product source inventory required')
    before = {name: hashlib.sha256((media_root/name).read_bytes()).hexdigest() for name in MEDIA_FILES}
    require(before == expected_hashes, 'Product source differs')
    config_module = compile_product(media_root/'config.py', '_launch_media_config')
    inspection_module = compile_product(media_root/'inspection.py', '_launch_media_inspection')
    config = config_module.MediaConfig(ffprobe_path=os.environ.get('SOCIAL_MEDIA_FFPROBE_PATH', ''))
    require(config.enabled is False, 'Inspector must not enable uploads')
    inspector = inspection_module.LocalInspector(config)
    available = inspector.available_mimes()
    require({'image/png', 'image/jpeg'} <= set(available), 'Image codecs unavailable')
    results = []
    with tempfile.TemporaryDirectory(prefix='auditgava-local-media-probe-') as directory:
        for index, fixture in enumerate(fixtures):
            require(type(fixture) is dict and set(fixture) == {'mime','width','height','base64','sha256'},
                    'Exact media fixture shape required')
            require(fixture['mime'] in ('image/png', 'image/jpeg'), 'Unsupported fixture MIME')
            raw = base64.b64decode(fixture['base64'], validate=True)
            require(0 < len(raw) <= 262144 and hashlib.sha256(raw).hexdigest() == fixture['sha256'],
                    'Fixture identity/byte bound refused')
            width = exact_integer(fixture['width'], 1, 1080)
            height = exact_integer(fixture['height'], 1, 1080)
            path = Path(directory)/f'fixture-{index}'
            path.write_bytes(raw)
            observed = inspector.inspect(path, fixture['mime'], len(raw))
            require(observed.mime_type == fixture['mime'] and observed.sha256 == fixture['sha256']
                    and observed.width == width and observed.height == height
                    and observed.byte_size == len(raw), 'Product inspection identity mismatch')
            refused = []
            for label, mime, length, replacement in [
                ('wrong_mime', 'image/jpeg' if fixture['mime']=='image/png' else 'image/png',len(raw),None),
                ('wrong_length',fixture['mime'],len(raw)+1,None),
                ('malformed',fixture['mime'],13,b'not an image!')]:
                if replacement is not None:
                    path.write_bytes(replacement)
                try:
                    inspector.inspect(path,mime,length)
                except inspection_module.InspectionFailure:
                    refused.append(label)
                else:
                    raise ValueError('Malformed media accepted')
            results.append({'mime_type': observed.mime_type, 'byte_size': observed.byte_size,
                            'sha256': observed.sha256, 'width':observed.width, 'height':observed.height,
                            'negative_controls_refused':refused})
    require({name: hashlib.sha256((media_root/name).read_bytes()).hexdigest() for name in MEDIA_FILES} == before,
            'Product source changed during inspection')
    return {'scope':'Actual bounded product image inspector only; no upload/object/asset/worker/provider operation',
            'product_sha256': before, 'images':results, 'temporary_files_removed':True,
            'available_mimes':list(available), 'video_inspection_exercised':False,
            'production_upload_or_delivery_accepted':False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-source', required=True)
    parser.add_argument('--images', action='store_true')
    parser.add_argument('--fixture-packet', type=Path)
    parser.add_argument('--media-root', type=Path, default=Path('/app/social/media'))
    args = parser.parse_args(argv)
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('Probe exceeded45seconds')))
    signal.alarm(45)
    flags = held_flags(os.environ, args.expected_source)
    start = cgroup_snapshot()
    record = {'at':datetime.now(timezone.utc).isoformat(),'source':args.expected_source,
              'flags':flags,'cgroup_before':start,'processes':process_inventory(),
              'database_references':{name:endpoint_metadata(os.environ.get(name)) for name in DB_REFERENCES},
              'worker_started':False,'uploads_enabled':False,'provider_calls':0,
              'capacity_accepted':False,'scope':'Current host observation with probe overhead; no sustained-load or launch acceptance'}
    if args.images:
        require(args.fixture_packet is not None, 'Exact fixture packet required')
        require(type(start.get('memory.current')) is int and type(start.get('memory.max')) is int
                and start['memory.max']-start['memory.current'] >= 96*1024*1024,
                'Insufficient bounded-probe headroom; no inference of accepted worker reserve')
        packet = read_packet(args.fixture_packet)
        record['media'] = inspect_images(args.media_root,packet['fixtures'],packet['product_sha256'])
    record['cgroup_after'] = cgroup_snapshot()
    require(held_flags(os.environ,args.expected_source)==flags,'Controls changed during observation')
    print('LAUNCH_RUNTIME_OBSERVATION '+json.dumps(record,sort_keys=True,allow_nan=False))
    return record


if __name__=='__main__':
    main()
