"""Small hostile-input controls for the replay boundary (no installs)."""
import json
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest

PACKET = Path(__file__).resolve().parent
api = runpy.run_path(str(PACKET / 'portable-replay.py'))


class ReplayBoundaries(unittest.TestCase):
    def test_missing_arguments_and_bad_roots_refuse_before_output(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'out'
            for mode in ['spec', 'blocker', 'standards']:
                for arguments, expected in [([], 'required'),
                    (['--baseline', '/batch14-absent', '--candidate', '/batch14-absent', '--output', str(out)], 'invalid frontend root')]:
                    child = subprocess.run(['python3', '-I', str(PACKET / 'portable-replay.py'), mode, *arguments], capture_output=True, text=True)
                    self.assertNotEqual(child.returncode, 0)
                    self.assertIn(expected, child.stderr)
                    self.assertFalse(out.exists())

    def test_fixture_tampering_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for path in [root, root / 'scripts']:
                if path != root:
                    path.mkdir()
            for name in ['.npmrc', '.NPMRC', 'npm-shrinkwrap.json']:
                p = root / name
                p.write_text('inert')
                with self.assertRaisesRegex(ValueError, 'unexpected project npm configuration'):
                    api['checked_root'](str(root))
                p.unlink()
            with self.assertRaisesRegex(ValueError, 'fixture source inventory mismatch'):
                api['checked_root'](str(root))
            with self.assertRaisesRegex(ValueError, 'invalid frontend root'):
                api['checked_root']('relative')

    def test_inherited_credentials_loaders_and_cache_are_not_forwarded(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.environ.copy()
            try:
                os.environ.update(NODE_OPTIONS='--require=/batch14-absent', DATABASE_URL='toy-secret', npm_config_cache='/batch14-unowned', HTTP_PROXY='toy-proxy')
                session = api['Session'](str(Path(d) / 'out'))
                try:
                    raw = session.run('env', [session.node, '-e', 'console.log(JSON.stringify(process.env))'], session.work)
                    env = json.loads(raw)
                    for name in ['NODE_OPTIONS', 'DATABASE_URL', 'HTTP_PROXY']:
                        self.assertNotIn(name, env)
                    self.assertEqual(env['npm_config_cache'], str(session.work / 'cache'))
                    self.assertEqual(env['npm_config_registry'], 'https://registry.npmjs.org/')
                finally:
                    session.close()
                self.assertFalse(session.work.exists())
            finally:
                os.environ.clear()
                os.environ.update(old)

    def test_failure_timeout_and_missing_child_clean_owned_temporary_root(self):
        with tempfile.TemporaryDirectory() as d:
            for name, argv, timeout in [('failure', ['-e', 'process.exit(71)'], 5),
                                        ('timeout', ['-e', 'setInterval(()=>{},1000)'], 0.05),
                                        ('missing-child', None, 5)]:
                session = api['Session'](str(Path(d) / name))
                try:
                    with self.assertRaises((RuntimeError, FileNotFoundError)):
                        session.run(name, [session.node, *argv] if argv else ['/batch14-missing-child'], session.work, timeout=timeout)
                finally:
                    session.close()
                self.assertFalse(session.work.exists())
                self.assertFalse((session.output / 'result.json').exists())
                for receipt in session.output.glob('*.receipt.json'):
                    self.assertFalse(json.loads(receipt.read_text())['verified'])

    def test_existing_and_measured_output_refused(self):
        with tempfile.TemporaryDirectory() as d:
            for p in [Path(d), PACKET / 'owned-output-must-not-exist']:
                with self.assertRaisesRegex(ValueError, 'fresh absolute|external'):
                    api['Session'](str(p))
                self.assertFalse((p / 'result.json').exists())

    def test_new_config_script_and_source_filetype_changes_refuse_success(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / 'frontend'
            for name in api['CONTRACT']:
                q = fixture / name
                q.parent.mkdir(parents=True, exist_ok=True)
                q.write_bytes(subprocess.check_output(['git', '-C', str(PACKET), 'show', api['FROZEN'] + ':frontend/' + name]))
            (fixture / 'node_modules/@istanbuljs/load-nyc-config').mkdir(parents=True)
            for name in ['.npmrc', 'scripts/new.cjs']:
                with self.subTest(name=name):
                    session = api['Session'](str(Path(directory) / ('out-' + name.replace('/', '-'))), (fixture,))
                    try:
                        with self.assertRaisesRegex(RuntimeError, 'replay command failed'):
                            session.run('add', [session.node, '-e', "require('node:fs').writeFileSync(process.argv[1], 'inert')", str(fixture / name)], session.work)
                    finally:
                        session.close()
                        (fixture / name).unlink()
                    self.assertFalse(json.loads((session.output / 'add.receipt.json').read_text())['verified'])
            source = fixture / next(n for n in api['CONTRACT'] if n.startswith('scripts/'))
            original = source.read_bytes()
            replacement = Path(directory) / 'same-bytes'
            replacement.write_bytes(original)
            session = api['Session'](str(Path(directory) / 'out-symlink'), (fixture,))
            try:
                with self.assertRaisesRegex(RuntimeError, 'replay command failed'):
                    session.run('link', [session.node, '-e', "const fs=require('node:fs');fs.unlinkSync(process.argv[1]);fs.symlinkSync(process.argv[2],process.argv[1]);", str(source), str(replacement)], session.work)
            finally:
                session.close()
                source.unlink()
                source.write_bytes(original)
            self.assertFalse(json.loads((session.output / 'link.receipt.json').read_text())['verified'])

    def test_installed_symlink_escape_cycle_and_unbound_module_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / 'frontend'
            for name in api['CONTRACT']:
                q = fixture / name
                q.parent.mkdir(parents=True, exist_ok=True)
                q.write_bytes(subprocess.check_output(['git', '-C', str(PACKET), 'show', api['FROZEN'] + ':frontend/' + name]))
            modules = fixture / 'node_modules'
            (modules / '@istanbuljs/load-nyc-config').mkdir(parents=True)
            outside = Path(directory) / 'outside'
            outside.mkdir()
            (outside / 'index.js').write_text('module.exports = 1;')
            for name, target in [('owned-link', outside), ('cycle', modules / 'cycle')]:
                link = modules / name
                link.symlink_to(target, target_is_directory=True)
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'installed.*link'):
                    api['checked_root'](str(fixture))
                link.unlink()
            (modules / '.bin').mkdir()
            link = modules / '.bin/escape'
            link.symlink_to(outside / 'index.js')
            with self.assertRaisesRegex(ValueError, 'installed.*link'):
                api['checked_root'](str(fixture))
            link.unlink()
            (modules / 'eslint-plugin-local').symlink_to(fixture / 'eslint-rules', target_is_directory=True)
            api['checked_root'](str(fixture))

    def test_completion_is_not_published_before_successful_cleanup(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'out'
            class CleanupFailure:
                def __init__(self, destination, roots):
                    self.output = Path(destination)
                    self.output.mkdir()
                    self.before = {}
                    self.node = 'node'
                    self.work = Path(directory)
                def run(self, *args, **kwargs):
                    return b''
                def close(self):
                    raise RuntimeError('injected cleanup failure')
            globals_ = api['replay'].__globals__
            old_session, old_root = globals_['Session'], globals_['checked_root']
            globals_['Session'], globals_['checked_root'] = CleanupFailure, lambda p, *a: Path(p)
            try:
                with self.assertRaisesRegex(RuntimeError, 'injected cleanup failure'):
                    api['replay'](SimpleNamespace(mode='blocker', baseline='/baseline', candidate='/candidate', output=str(output)))
                self.assertFalse((output / 'result.json').exists())
            finally:
                globals_['Session'], globals_['checked_root'] = old_session, old_root

    def test_packet_checksum_rejects_missing_extra_changed_and_linked_bytes(self):
        verify = runpy.run_path(str(PACKET / 'verify-packet.py'))['verify']
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / 'data'
            data.write_text('original')
            manifest = root / 'SHA256SUMS.json'
            manifest.write_text(json.dumps({'data': hashlib.sha256(data.read_bytes()).hexdigest()}))
            self.assertEqual(verify(root), 1)
            for content in ['changed', '']:
                data.write_text(content)
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    verify(root)
            data.unlink()
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                verify(root)
            data.write_text('original')
            extra = root / 'extra'
            extra.write_text('extra')
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                verify(root)
            extra.unlink()
            extra.symlink_to(data)
            with self.assertRaisesRegex(ValueError, 'non-regular'):
                verify(root)
            extra.unlink()
            for bad in [{}, [], {'../escape': 'hash'}, {'data': True}]:
                manifest.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    verify(root)


if __name__ == '__main__':
    unittest.main()
