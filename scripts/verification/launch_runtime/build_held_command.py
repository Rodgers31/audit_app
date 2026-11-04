"""Print a source-bound parent command; does not execute it or write a receipt."""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import stat
import zlib

# Fixed review inputs, not computed from the files supplied to build(). Updating
# any pin requires a new source review; dirty input bytes cannot approve themselves.
REVIEWED_SHA256 = {
    'probe.py': '7ad09a3d164cdbd963236c4c463ef2b4825ceb53af31b46be56ba57f6b1f7a2c',
    'fixtures.json': 'de73898162fc7ca5b085be6b0e20e7bfdd8b361ae175262ab7b9e90c5139617a',
    'tiny-h264.mp4': '28b9c19e60fa06579819d67324d8d3b05ab6605b3ef3170f2e3d471e39745a6a',
    'held_packet.py': '6fc2e8db5884251806f1db65ce54dde25428d84d8a91014655a584f8be03dff8',
}


def build(root):
    rows = []
    for name, digest in REVIEWED_SHA256.items():
        path = root / name
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Regular packet source required')
        with path.open('rb') as stream:
            raw = stream.read(32769)
        if not 0 < len(raw) <= 32768:
            raise ValueError('Packet source byte bound')
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('Packet source differs from reviewed manifest')
        rows.append((name, digest, base64.b64encode(zlib.compress(raw, 9)).decode('ascii')))
    # Literal data only: no credential, .env, platform SDK or shell expansion.
    # Both sides use independent review pins, not a digest self-supplied by a row.
    return '''python -B -I - <<'AUDITGAVA_HELD_PACKET'
import base64, hashlib, json, signal, stat, tempfile, time, zlib
from pathlib import Path
def need(value):
    if value is not True:
        raise ValueError('Packet transport refused')
def expire(*_):
    raise TimeoutError('Packet deadline exceeded')
def captured_bytes(path):
    need(stat.S_ISREG(path.lstat().st_mode))
    with path.open('rb') as stream:
        raw = stream.read(32769)
    need(0 < len(raw) <= 32768)
    return raw
def arm(deadline):
    remaining = deadline - time.monotonic()
    need(0 < remaining <= 80)
    signal.setitimer(signal.ITIMER_REAL, remaining)
signal.signal(signal.SIGALRM, expire)
transport_deadline = time.monotonic() + 80
arm(transport_deadline)
try:
    pins = ''' + repr(REVIEWED_SHA256) + '''
    rows = ''' + repr(rows) + '''
    need(type(rows) is list and len(rows) == len(pins))
    need(all(type(row) is tuple and len(row) == 3 for row in rows))
    need(tuple(row[0] for row in rows) == tuple(pins))
    captured = {}
    for name, digest, encoded in rows:
        need(type(name) is str and type(digest) is str and digest == pins[name])
        need(type(encoded) is str and 0 < len(encoded) <= 65536)
        decoder = zlib.decompressobj()
        raw = decoder.decompress(base64.b64decode(encoded, validate=True), 32769)
        need(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail)
        need(0 < len(raw) <= 32768 and hashlib.sha256(raw).hexdigest() == pins[name])
        captured[name] = raw
    with tempfile.TemporaryDirectory(prefix='auditgava-held-followthrough-') as directory:
        root = Path(directory)
        for name, raw in captured.items():
            with (root / name).open('xb') as stream:
                stream.write(raw)
            (root / name).chmod(0o600)
        namespace = {'__name__': '_parent_verified_held_packet'}
        exec(compile(captured['held_packet.py'], str(root / 'held_packet.py'), 'exec', dont_inherit=True), namespace)
        # observe() is also a direct entry point: its main() alarm is not assumed.
        # Restore the original outer deadline even when the inner alarm refuses,
        # leaving only the remaining transport budget for owned-file cleanup.
        arm(min(transport_deadline, time.monotonic() + 75))
        try:
            record = namespace['observe'](root, Path('/app/social/media'))
        finally:
            arm(transport_deadline)
        need(all(captured_bytes(root / name) == raw for name, raw in captured.items()))
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
    signal.setitimer(signal.ITIMER_REAL, 0)
AUDITGAVA_HELD_PACKET
'''


if __name__ == '__main__':
    print(build(Path(__file__).resolve().parent), end='')
