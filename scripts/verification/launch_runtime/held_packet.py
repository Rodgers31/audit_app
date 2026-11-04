"""Parent-operated, offline tiny-codec observation. Never a capacity acceptance.

The external command must verify this file before compiling its captured bytes.
No application startup, DB connection, provider call or durable receipt write.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import stat
import subprocess
import tempfile
import time

SOURCE = 'f0f4705e9561e2e42edd93fc747e8bff24468fae'
PINS = {
    'probe.py': '7ad09a3d164cdbd963236c4c463ef2b4825ceb53af31b46be56ba57f6b1f7a2c',
    'fixtures.json': 'de73898162fc7ca5b085be6b0e20e7bfdd8b361ae175262ab7b9e90c5139617a',
    'tiny-h264.mp4': '28b9c19e60fa06579819d67324d8d3b05ab6605b3ef3170f2e3d471e39745a6a',
}
BINARY = Path('/usr/bin/ffprobe')
BINARY_SHA256 = 'cefc5f81c0b18429cdbf8fa5a89e1e9c759235e10f93f9b329ff1b2fdff26f46'
PREFIX = 'HELD_RUNTIME_PACKET '


def need(value, message):
    if value is not True:
        raise ValueError(message)


def pinned_bytes(path, digest, limit):
    need(stat.S_ISREG(path.lstat().st_mode), 'Regular non-symlink input required')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    need(0 < len(raw) <= limit and hashlib.sha256(raw).hexdigest() == digest,
         'Input identity or byte bound refused')
    return raw


def load_probe(root):
    raw = pinned_bytes(root / 'probe.py', PINS['probe.py'], 32768)
    namespace = {'__name__': '_held_packet_probe'}
    exec(compile(raw, str(root / 'probe.py'), 'exec', dont_inherit=True), namespace)
    return namespace


def check_resources(snapshot):
    need(type(snapshot) is dict, 'Missing resource snapshot')
    current, maximum = snapshot.get('memory.current'), snapshot.get('memory.max')
    need(type(current) is int and type(maximum) is int
         and maximum == 512 * 1024 * 1024 and 0 <= current <= maximum
         and maximum - current >= 96 * 1024 * 1024,
         'Tiny-probe headroom unavailable; no accepted worker reserve')
    cpu = snapshot.get('cpu.max')
    need(type(cpu) is dict and type(cpu.get('quota_usec')) is int
         and type(cpu.get('period_usec')) is int and cpu['period_usec'] > 0
         and cpu['quota_usec'] * 2 == cpu['period_usec'], 'Expected half-core quota required')
    events = snapshot.get('memory.events')
    need(type(events) is dict and all(type(events.get(key)) is int and events[key] == 0
         for key in ('oom', 'oom_kill', 'oom_group_kill')), 'OOM evidence unavailable or nonzero')


def check_runtime():
    need(platform.system() == 'Linux' and platform.machine() == 'x86_64'
         and platform.python_version() == '3.12.16', 'Intended runtime identity required')
    need(os.environ.get('SOCIAL_MEDIA_FFPROBE_PATH') == str(BINARY),
         'Configured ffprobe path changed')


def binary_identity():
    raw = pinned_bytes(BINARY, BINARY_SHA256, 16 * 1024 * 1024)
    need(os.access(BINARY, os.X_OK), 'Executable ffprobe required')
    return hashlib.sha256(raw).hexdigest()


def inspect_video(probe, media_root, raw):
    need(type(raw) is bytes and len(raw) == 1844
         and hashlib.sha256(raw).hexdigest() == PINS['tiny-h264.mp4'], 'Video fixture identity refused')
    # Verify every product source before any module executes. The actual child
    # and its parent use only this private snapshot, as in the reviewed probe.
    sources = {name: probe['product_source'](media_root / name) for name in probe['MEDIA_FILES']}
    before_binary = binary_identity()  # Before even `-version` can execute.
    binary_bytes = pinned_bytes(BINARY, before_binary, 16 * 1024 * 1024)
    with tempfile.TemporaryDirectory(prefix='auditgava-held-video-') as directory:
        root = Path(directory)
        for name, source in sources.items():
            (root / name).write_bytes(source)
        private_binary = root / 'ffprobe'
        private_binary.write_bytes(binary_bytes)
        private_binary.chmod(0o500)
        config = probe['compile_product'](root / 'config.py', '_held_video_config').MediaConfig(
            ffprobe_path=str(private_binary))
        need(config.enabled is False, 'Uploads must stay off')
        module = probe['compile_product'](root / 'inspection.py', '_held_video_inspection')
        inspector = module.LocalInspector(config)
        need('video/mp4' in inspector.available_mimes(), 'MP4 inspection unavailable')
        with tempfile.TemporaryFile() as output:
            result = subprocess.run([str(private_binary), '-version'], stdout=output,
                stderr=subprocess.DEVNULL, timeout=2, check=False,
                env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
            output.seek(0)
            version = output.read(4097)
        need(result.returncode == 0 and 0 < len(version) <= 4096
             and version.startswith(b'ffprobe version '), 'ffprobe version unavailable')
        path = root / 'synthetic.mp4'
        path.write_bytes(raw)
        value = inspector.inspect(path, 'video/mp4', len(raw))
        need(value.mime_type == 'video/mp4' and value.sha256 == PINS['tiny-h264.mp4']
             and type(value.byte_size) is int and value.byte_size == 1844
             and type(value.width) is int and value.width == 64
             and type(value.height) is int and value.height == 32
             and type(value.duration_ms) is int and value.duration_ms == 1000
             and type(value.frame_rate) in (int, float) and value.frame_rate == 10
             and value.codec_metadata == {'video_codec': 'h264', 'audio_codec': None},
             'Video fixture inspection mismatch')
        refused = []
        for label, mime, length, replacement in (
                ('wrong_mime', 'image/png', len(raw), None),
                ('wrong_length', 'video/mp4', len(raw) + 1, None),
                ('malformed', 'video/mp4', len(raw), b'\0' * len(raw))):
            if replacement is not None:
                path.write_bytes(replacement)
            try:
                inspector.inspect(path, mime, length)
            except module.InspectionFailure:
                refused.append(label)
            else:
                raise ValueError('Negative video control accepted')
        need(all(probe['product_source'](root / name) == source
                 for name, source in sources.items()), 'Private product snapshot changed')
        need(pinned_bytes(private_binary, before_binary, 16 * 1024 * 1024) == binary_bytes,
             'Private binary snapshot changed')
    need(not root.exists(), 'Private video directory remained')
    need(all(probe['product_source'](media_root / name) == source
             for name, source in sources.items()), 'Original product source changed')
    need(binary_identity() == before_binary, 'ffprobe changed')
    return {'fixture_sha256': value.sha256, 'byte_size': value.byte_size,
            'width': value.width, 'height': value.height, 'duration_ms': value.duration_ms,
            'frame_rate': value.frame_rate, 'codec_metadata': value.codec_metadata,
            'negative_controls_refused': refused, 'temporary_files_removed': True,
            'binary_sha256': before_binary, 'binary_version': version.splitlines()[0].decode('ascii')}


def observe(root, media_root):
    started = time.monotonic()
    probe = load_probe(root)
    flags = probe['held_flags'](os.environ, SOURCE)
    check_runtime()
    inputs = {name: pinned_bytes(root / name, digest, 32768) for name, digest in PINS.items()}
    products = {name: probe['product_source'](media_root / name) for name in probe['MEDIA_FILES']}
    before = probe['cgroup_snapshot']()
    check_resources(before)
    processes_before = probe['process_inventory']()
    # JSON parser executes against the exact captured, pinned packet bytes in a
    # private directory, so a caller cannot swap it between verification/read.
    with tempfile.TemporaryDirectory(prefix='auditgava-held-images-') as directory:
        fixture_path = Path(directory) / 'fixtures.json'
        fixture_path.write_bytes(inputs['fixtures.json'])
        packet = probe['read_packet'](fixture_path)
        images = probe['inspect_images'](media_root, packet['fixtures'], packet['product_sha256'])
    need(not Path(directory).exists(), 'Private image packet directory remained')
    between = probe['cgroup_snapshot']()
    check_resources(between)
    need(probe['held_flags'](os.environ, SOURCE) == flags,
         'Controls changed before video inspection')
    video = inspect_video(probe, media_root, inputs['tiny-h264.mp4'])
    processes_after = probe['process_inventory']()
    after = probe['cgroup_snapshot']()
    check_resources(after)
    need(probe['held_flags'](os.environ, SOURCE) == flags, 'Controls changed during packet')
    need(all(pinned_bytes(root / name, digest, 32768) == inputs[name]
             for name, digest in PINS.items()), 'Packet source changed')
    need(all(probe['product_source'](media_root / name) == raw
             for name, raw in products.items()), 'Product source changed during packet')
    elapsed = time.monotonic() - started
    need(0 < elapsed < 75, 'Packet deadline exceeded')
    return {'at': datetime.now(timezone.utc).isoformat(), 'source': SOURCE,
            'flags': flags, 'runtime': {'os': platform.system(), 'arch': platform.machine(),
                                       'python': platform.python_version()},
            'input_sha256': dict(PINS), 'product_sha256': dict(probe['PRODUCT_SHA256']),
            'cgroup_before': before, 'cgroup_between': between, 'cgroup_after': after,
            'processes_before': processes_before, 'processes_after': processes_after,
            'images': images, 'video': video, 'elapsed_seconds': elapsed,
            'worker_started': False, 'provider_calls': 0, 'database_connections': 0,
            'uploads_enabled': False, 'capacity_accepted': False, 'launch_accepted': False,
            'scope': 'Tiny codecs and instantaneous OFF-state host samples; separate protected witnesses required'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet-root', type=Path, required=True)
    parser.add_argument('--media-root', type=Path, default=Path('/app/social/media'))
    args = parser.parse_args(argv)
    previous = signal.signal(signal.SIGALRM,
        lambda *_: (_ for _ in ()).throw(TimeoutError('Packet deadline exceeded')))
    signal.alarm(75)
    try:
        record = observe(args.packet_root, args.media_root)
        raw = json.dumps(record, sort_keys=True, allow_nan=False)
        need(len(raw) <= 65536, 'Packet output bound')
        print(PREFIX + raw)
        return record
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # No exception text, local paths, credentials or provider bodies escape.
        print('HELD_RUNTIME_REFUSED no completion observation emitted')
        raise SystemExit(1) from None
