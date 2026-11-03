"""Print a source-bound parent command; does not execute it or write a receipt."""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import zlib


def build(root):
    names = ('probe.py', 'fixtures.json', 'tiny-h264.mp4', 'held_packet.py')
    rows = []
    for name in names:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Regular packet source required')
        raw = path.read_bytes()
        if not 0 < len(raw) <= 32768:
            raise ValueError('Packet source byte bound')
        rows.append((name, hashlib.sha256(raw).hexdigest(),
                     base64.b64encode(zlib.compress(raw, 9)).decode('ascii')))
    # Literal data only: no credential, .env, platform SDK or shell expansion.
    return '''python -B -I - <<'AUDITGAVA_HELD_PACKET'
import base64, hashlib, json, signal, tempfile, zlib
from pathlib import Path
def need(value):
    if value is not True:
        raise ValueError('Packet transport refused')
def expire(*_):
    raise TimeoutError('Packet deadline exceeded')
signal.signal(signal.SIGALRM, expire)
signal.alarm(80)
try:
    rows = ''' + repr(rows) + '''
    captured = {}
    for name, digest, encoded in rows:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(base64.b64decode(encoded, validate=True), 32769)
        need(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail)
        need(0 < len(raw) <= 32768 and hashlib.sha256(raw).hexdigest() == digest)
        captured[name] = raw
    with tempfile.TemporaryDirectory(prefix='auditgava-held-followthrough-') as directory:
        root = Path(directory)
        for name, raw in captured.items():
            with (root / name).open('xb') as stream:
                stream.write(raw)
            (root / name).chmod(0o600)
        namespace = {'__name__': '_parent_verified_held_packet'}
        exec(compile(captured['held_packet.py'], str(root / 'held_packet.py'), 'exec', dont_inherit=True), namespace)
        record = namespace['observe'](root, Path('/app/social/media'))
        need(all((root / name).read_bytes() == raw for name, raw in captured.items()))
    need(not root.exists())
    record['executed_packet_sha256'] = hashlib.sha256(captured['held_packet.py']).hexdigest()
    record['transport_temporary_files_removed'] = True
    result = json.dumps(record, sort_keys=True, allow_nan=False)
    need(len(result) <= 65536)
    print('HELD_RUNTIME_PACKET ' + result)
except Exception:
    print('HELD_RUNTIME_REFUSED no completion observation emitted')
    raise SystemExit(1) from None
finally:
    signal.alarm(0)
AUDITGAVA_HELD_PACKET
'''


if __name__ == '__main__':
    print(build(Path(__file__).resolve().parent), end='')
