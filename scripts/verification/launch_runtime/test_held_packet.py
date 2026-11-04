"""Offline packet tests. Injected host readings do not attest a production host."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
MEDIA = ROOT.parents[2] / 'backend/social/media'
spec = importlib.util.spec_from_file_location('held_packet', ROOT / 'held_packet.py')
packet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packet)


def resources():
    return {'memory.current': 300 * 1024 * 1024, 'memory.max': 512 * 1024 * 1024,
            'memory.events': {'oom': 0, 'oom_kill': 0, 'oom_group_kill': 0},
            'cpu.max': {'quota_usec': 50000, 'period_usec': 100000}}


def held_environment():
    return {'RENDER_GIT_COMMIT': packet.SOURCE, 'AUTO_SEEDER_ENABLED': 'false',
            'AUTO_WARMUP_ENABLED': 'false', 'SOCIAL_MEDIA_FFPROBE_PATH': '/usr/bin/ffprobe'}


class PacketTests(unittest.TestCase):
    def test_exact_input_inventory_and_regular_file_refusals(self):
        for name, digest in packet.PINS.items():
            self.assertTrue(packet.pinned_bytes(ROOT / name, digest, 32768))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input'
            for raw in (b'', b'changed', b'x' * 32769):
                path.write_bytes(raw)
                with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                    packet.pinned_bytes(path, packet.PINS['probe.py'], 32768)
            path.unlink()
            path.symlink_to(ROOT / 'probe.py')
            with self.assertRaises(ValueError):
                packet.pinned_bytes(path, packet.PINS['probe.py'], 32768)
            with self.assertRaises(FileNotFoundError):
                packet.pinned_bytes(path.with_name('absent'), packet.PINS['probe.py'], 32768)

    def test_untrusted_probe_refuses_before_marker_executes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'marker'
            (root / 'probe.py').write_text('from pathlib import Path\nPath(' + repr(str(marker)) + ').touch()')
            with self.assertRaises(ValueError):
                packet.load_probe(root)
            self.assertFalse(marker.exists())

    def test_resource_types_and_missing_telemetry_refuse(self):
        packet.check_resources(resources())
        bad = [None, {}, {'memory.current': 0}]
        for key in ('memory.current', 'memory.max'):
            for value in (True, False, -1, 0.0, float('nan'), float('inf'), '536870912', None):
                item = resources(); item[key] = value; bad.append(item)
        for key in ('oom', 'oom_kill', 'oom_group_kill'):
            for value in (True, 1, None):
                item = resources(); item['memory.events'][key] = value; bad.append(item)
        item = resources(); item['memory.current'] = 417 * 1024 * 1024; bad.append(item)
        for value in ({}, None, {'quota_usec': True, 'period_usec': 2},
                      {'quota_usec': 0, 'period_usec': 0}, {'quota_usec': 100000, 'period_usec': 100000}):
            item = resources(); item['cpu.max'] = value; bad.append(item)
        for item in bad:
            with self.subTest(item=repr(item)), self.assertRaises(ValueError):
                packet.check_resources(item)

    def test_missing_warmup_refuses_before_runtime_or_codec_execution(self):
        values = held_environment(); values.pop('AUTO_WARMUP_ENABLED')
        with patch.dict(os.environ, values, clear=True), patch.object(packet, 'check_runtime') as runtime:
            with self.assertRaisesRegex(ValueError, 'explicit false'):
                packet.observe(ROOT, MEDIA)
            runtime.assert_not_called()

    def test_wrong_runtime_or_configured_binary_refuses(self):
        with patch.dict(os.environ, held_environment(), clear=True), \
                patch.object(packet.platform, 'system', return_value='Linux'), \
                patch.object(packet.platform, 'machine', return_value='x86_64'), \
                patch.object(packet.platform, 'python_version', return_value='3.12.16'):
            packet.check_runtime()
            for key, value in (('system', 'Darwin'), ('machine', 'arm64'), ('python_version', '3.13.9')):
                with self.subTest(key=key), patch.object(packet.platform, key, return_value=value), self.assertRaises(ValueError):
                    packet.check_runtime()
            os.environ['SOCIAL_MEDIA_FFPROBE_PATH'] = '/other/binary'
            with self.assertRaises(ValueError):
                packet.check_runtime()

    def test_unreviewed_binary_and_bad_video_refuse_before_execution(self):
        probe = packet.load_probe(ROOT)
        raw = (ROOT / 'tiny-h264.mp4').read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'ffprobe'
            marker = Path(directory) / 'marker'
            binary.write_text('#!/bin/sh\ntouch ' + str(marker) + '\n')
            binary.chmod(0o700)
            with patch.object(packet, 'BINARY', binary), self.assertRaises(ValueError):
                packet.inspect_video(probe, MEDIA, raw)
            self.assertFalse(marker.exists())
        for invalid in (None, b'', b'changed', True):
            with self.subTest(invalid=invalid), patch.object(packet, 'binary_identity') as binary:
                with self.assertRaises(ValueError):
                    packet.inspect_video(probe, MEDIA, invalid)
                binary.assert_not_called()

    def test_changed_product_child_never_executes(self):
        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / 'media'
            shutil.copytree(MEDIA, media)
            marker = Path(directory) / 'marker'
            (media / 'inspection_child.py').write_text('from pathlib import Path\nPath(' + repr(str(marker)) + ').touch()')
            with patch.object(packet, 'binary_identity') as binary, self.assertRaises(ValueError):
                packet.inspect_video(packet.load_probe(ROOT), media, (ROOT / 'tiny-h264.mp4').read_bytes())
            binary.assert_not_called()
            self.assertFalse(marker.exists())

    def test_native_codecs_with_injected_host_samples_and_local_binary(self):
        # Actual PNG/JPEG/H264 children on native local Python. Runtime/cgroup
        # samples and binary pin below are injected; no Linux acceptance follows.
        binary = Path(shutil.which('ffprobe') or '/absent/ffprobe').resolve()
        self.assertTrue(binary.is_file(), 'Existing local ffprobe required; no installation')
        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        real_load = packet.load_probe
        def local_probe(root):
            namespace = real_load(root)
            namespace['cgroup_snapshot'] = resources
            namespace['process_inventory'] = lambda: [{'pid': os.getpid(), 'role': 'probe'}]
            return namespace
        calls = []
        run = subprocess.run
        def checked_run(argv, **kwargs):
            calls.append((argv, kwargs))
            self.assertEqual(kwargs['env'], {'PATH': '/usr/bin:/bin', 'LANG': 'C'})
            return run(argv, **kwargs)
        values = {**held_environment(), 'DATABASE_URL': 'toy-secret-db', 'SOCIAL_MEDIA_SECRET_KEY': 'toy-secret-media'}
        with patch.dict(os.environ, values, clear=True), patch.object(packet, 'load_probe', side_effect=local_probe), \
                patch.object(packet, 'check_runtime'), patch.object(packet, 'BINARY', binary), \
                patch.object(packet, 'BINARY_SHA256', digest), patch.object(subprocess, 'run', side_effect=checked_run):
            result = packet.observe(ROOT, MEDIA)
        self.assertEqual(len(result['images']['images']), 2)
        self.assertEqual(result['video']['negative_controls_refused'], ['wrong_mime', 'wrong_length', 'malformed'])
        self.assertTrue(result['video']['temporary_files_removed'])
        self.assertIs(result['capacity_accepted'], False)
        self.assertIs(result['launch_accepted'], False)
        self.assertEqual(result['database_connections'], 0)
        self.assertNotIn('toy-secret', json.dumps(result))
        self.assertGreater(len(calls), 6)
        for argv, _ in calls:
            self.assertNotIn(str(binary), argv, 'Only private pinned binary snapshot may execute')

    def test_packet_never_prints_completion_after_failure(self):
        with patch.object(packet, 'observe', side_effect=ValueError('toy-secret')), \
                patch('builtins.print') as output:
            with self.assertRaises(ValueError):
                packet.main(['--packet-root', str(ROOT)])
            output.assert_not_called()

    def test_controls_changed_between_codecs_refuse_before_video(self):
        real_probe = packet.load_probe(ROOT)
        for key, value in (('SOCIAL_MEDIA_ENABLED', 'true'),
                           ('RENDER_GIT_COMMIT', '0' * 40)):
            with self.subTest(key=key):
                probe = dict(real_probe)
                snapshots = []
                def snapshot():
                    snapshots.append(True)
                    if len(snapshots) == 2:
                        os.environ[key] = value
                    return resources()
                probe.update(cgroup_snapshot=snapshot,
                             process_inventory=lambda: [{'pid': 1, 'role': 'probe'}],
                             inspect_images=lambda *_: {'scope': 'inert fixture'})
                with patch.dict(os.environ, held_environment(), clear=True), \
                        patch.object(packet, 'load_probe', return_value=probe), \
                        patch.object(packet, 'check_runtime'), \
                        patch.object(packet, 'inspect_video', return_value={'scope': 'inert fixture'}) as video:
                    with self.assertRaises(ValueError):
                        packet.observe(ROOT, MEDIA)
                    self.assertEqual(video.call_count, 0, 'Changed controls reached H264 inspection')
                self.assertEqual(len(snapshots), 2, 'Video transition was not reached')

    def test_final_inventory_cannot_escape_flags_source_or_deadline_guards(self):
        real_probe = packet.load_probe(ROOT)
        for mutation in ('flags', 'source', 'deadline'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                media = Path(directory) / 'media'
                shutil.copytree(MEDIA, media)
                clock = [0.0]
                inventories = []
                probe = dict(real_probe)
                def inventory():
                    inventories.append(True)
                    clock[0] = 1.0
                    if len(inventories) == 2:
                        if mutation == 'flags':
                            os.environ['SOCIAL_MEDIA_ENABLED'] = 'true'
                        elif mutation == 'source':
                            (media / 'inspection.py').write_bytes(b'changed')
                        else:
                            clock[0] = 76.0
                    return [{'pid': 1, 'role': 'probe'}]
                probe.update(cgroup_snapshot=resources, process_inventory=inventory,
                             inspect_images=lambda *_: {'scope': 'inert fixture'})
                with patch.dict(os.environ, held_environment(), clear=True), \
                        patch.object(packet, 'load_probe', return_value=probe), \
                        patch.object(packet, 'check_runtime'), \
                        patch.object(packet, 'inspect_video', return_value={'scope': 'inert fixture'}), \
                        patch.object(packet.time, 'monotonic', side_effect=lambda: clock[0]):
                    with self.assertRaises(ValueError):
                        packet.observe(ROOT, media)
                self.assertEqual(len(inventories), 2, 'Final inventory guard was not reached')


if __name__ == '__main__':
    unittest.main(verbosity=2)
