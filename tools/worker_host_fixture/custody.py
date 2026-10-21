"""Bounded export of PUBLIC INERT fixture artifacts, never production data.

Complete source-bound chunk sets are required on download. A truncated log must
not become an accepted recovery artifact. This is backup/restore evidence, not
a claim that Render's ephemeral filesystem persists across deployment.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zlib


def receipt_descriptor(argv):
    import fcntl
    import stat
    flag = '--supervisor-receipt-fd'
    if type(argv) is not list or argv.count(flag) != 1:
        raise ValueError('One authentic receipt descriptor required')
    index = argv.index(flag)
    value = argv[index+1] if index + 1 < len(argv) else None
    if type(value) is not str or not re.fullmatch('[1-9][0-9]{0,2}', value) or not 3 <= int(value) < 512:
        raise ValueError('Non-stdio bounded receipt descriptor required')
    fd = int(value)
    info = os.fstat(fd)
    if (not stat.S_ISFIFO(info.st_mode) or info.st_uid != os.getuid()
            or fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != os.O_WRONLY):
        raise ValueError('Owned write-only receipt pipe required')
    return fd


def export(name, content):
    if type(name) is not str or not re.fullmatch('[a-z][a-z0-9_-]{0,40}', name):
        raise ValueError('Artifact name required')
    if type(content) is not bytes or not 0 < len(content) <= 4 * 1024 ** 2:
        raise ValueError('Artifact bound')
    encoded = base64.b64encode(zlib.compress(content)).decode('ascii')
    if len(encoded) > 256 * 1024:
        raise ValueError('Compressed artifact bound')
    identity = json.loads(Path('/evidence/identity.json').read_text())
    pieces = [encoded[i:i+1536] for i in range(0, len(encoded), 1536)]
    for index, piece in enumerate(pieces):
        print('HOST_FIXTURE_ARTIFACT ' + json.dumps(dict(version=1, name=name,
            run_id=identity['run_id'], manifest_sha256=identity['manifest_sha256'],
            generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            index=index, count=len(pieces), sha256=hashlib.sha256(content).hexdigest(),
            size=len(content), data=piece), sort_keys=True), flush=True)


def closure_backup(payload):
    # Only the authentic native receipt schema is accepted. No proof is created
    # or amended here. The caller still writes the original bytes to its pipe.
    if type(payload) is not bytes or not 0 < len(payload) <= 4096:
        raise ValueError('Bounded native receipt required')
    def unique(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError('Duplicate native receipt key')
            result[key] = item
        return result
    value = json.loads(payload, object_pairs_hook=unique)
    expected = {'version', 'owner_id', 'generation', 'providers_closed', 'executor_closed', 'claims_drained'}
    from uuid import UUID
    if (type(value) is not dict or set(value) != expected or type(value['version']) is not int
            or value['version'] != 1 or type(value['generation']) is not int or value['generation'] < 1
            or type(value['owner_id']) is not str or str(UUID(value['owner_id'])) != value['owner_id']
            or any(value[k] is not True for k in ('providers_closed', 'executor_closed', 'claims_drained'))):
        raise ValueError('Authentic native closure schema required')
    # Startup already performed the post-exec FD census. At shutdown the real
    # worker still owns its wakeup pipe until after receipt publication; those
    # legitimate descriptors must not be mistaken for a jail escape.
    from bounded_profile import inert_environment
    inert_environment(dict(os.environ))
    from isolation import content_boundary
    if (os.getuid() != 10001 or content_boundary() is not True
            or Path('/').stat().st_uid != 65534 or not Path('/manifest.json').is_file()):
        raise RuntimeError('Isolated immutable fixture root required')
    target = Path('/evidence/closure.dump')
    if target.exists():
        raise ValueError('Fresh closure dump required')
    # A separate Python exec sets a finite regular-file limit before pg_dump;
    # no unsafe preexec callback in the previously threaded native process.
    code = ("import os,resource;resource.setrlimit(resource.RLIMIT_FSIZE,(4194304,4194304));"
            "os.execv('/usr/lib/postgresql/17/bin/pg_dump',"
            "['pg_dump','-h','127.0.0.2','-U','postgres','-Fc','--no-owner','--no-privileges',"
            "'-f','/evidence/closure.dump','b15_worker_capacity'])")
    process = subprocess.Popen([sys.executable, '-I', '-B', '-S', '-c', code],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={'PATH':'/usr/local/bin:/usr/bin:/bin'}, close_fds=True, start_new_session=True)
    try:
        if process.wait(timeout=15) != 0:
            raise RuntimeError('Fixture backup failed')
    finally:
        if process.poll() is None:
            os.killpg(process.pid, 9)
            process.wait(timeout=3)
    content = target.read_bytes()
    export('closure_dump', content)
    export('native_receipt', payload)
    return True
