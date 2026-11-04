"""Execute generated transport offline; injected observer is never a host proof."""
import ast
import base64
import builtins
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('held_command_builder', ROOT / 'build_held_command.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def body(command):
    opening = "python -B -I - <<'AUDITGAVA_HELD_PACKET'\n"
    closing = 'AUDITGAVA_HELD_PACKET\n'
    if not command.startswith(opening) or not command.endswith(closing):
        raise ValueError('Unexpected generated shell envelope')
    return command[len(opening):-len(closing)]


def change_rows(command, edit):
    tree = ast.parse(body(command))
    matches = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == 'rows' for target in node.targets)]
    if len(matches) != 1:
        raise ValueError('Expected one literal captured-row assignment')
    node = matches[0]
    rows = ast.literal_eval(node.value)
    edit(rows)
    node.value = ast.parse(repr(rows), mode='eval').body
    return ast.unparse(tree)


class TransportTests(unittest.TestCase):
    def execute(self, code, observer=None, real_runner=False):
        """Real wrapper/tempfiles/signals; only runner execution is injected."""
        output = io.StringIO()
        calls, directories, budgets = [], [], []
        original_compile = builtins.compile
        old_handler = signal.getsignal(signal.SIGALRM)
        old_timer = signal.getitimer(signal.ITIMER_REAL)
        def observe(root, media):
            directories.append(root)
            budgets.append(signal.getitimer(signal.ITIMER_REAL)[0])
            self.assertEqual(media, Path('/app/social/media'))
            self.assertEqual({p.name for p in root.iterdir()},
                             {'probe.py', 'fixtures.json', 'tiny-h264.mp4', 'held_packet.py'})
            if observer is not None:
                return observer(root, media)
            return {'fixture_only': True, 'capacity_accepted': False, 'launch_accepted': False}
        def compile_runner(raw, filename, mode, **kwargs):
            self.assertTrue(str(filename).endswith('/held_packet.py'))
            calls.append(raw)
            if real_runner:
                return original_compile(raw, filename, mode, **kwargs)
            return original_compile("observe = __import__('_held_transport_fixture').observe\n",
                                    filename, mode)
        module = types.SimpleNamespace(observe=observe)
        try:
            with patch.dict(sys.modules, {'_held_transport_fixture': module}), \
                    patch.dict(vars(builtins), {'compile': compile_runner}), \
                    contextlib.redirect_stdout(output):
                try:
                    exec(original_compile(code, '<generated-transport>', 'exec'), {})
                    exit_code = 0
                except SystemExit as exc:
                    exit_code = exc.code
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
            if old_timer[0]:
                signal.setitimer(signal.ITIMER_REAL, *old_timer)
        return exit_code, output.getvalue(), calls, directories, budgets

    def test_builder_refuses_changed_runner_before_generating_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('probe.py', 'fixtures.json', 'tiny-h264.mp4', 'held_packet.py'):
                shutil.copyfile(ROOT / name, root / name)
            path = root / 'held_packet.py'
            path.write_bytes(b'# unreviewed runner\n' + path.read_bytes())
            with self.assertRaises(ValueError):
                builder.build(root)

    def test_builder_never_reads_more_than_the_packet_byte_budget(self):
        original_open = Path.open
        reads = []
        owner = self
        class GuardedStream:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): return self.stream.__exit__(*args)
            def read(self, size=-1):
                owner.assertTrue(0 < size <= 32769, 'unbounded packet source read')
                reads.append(size)
                return self.stream.read(size)
        def open_source(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            return GuardedStream(stream)
        with patch.object(Path, 'open', new=open_source):
            command = builder.build(ROOT)
        self.assertTrue(command.startswith('python -B -I -'))
        self.assertEqual(len(reads), 4)

    def test_generated_transport_executes_pinned_bytes_and_cleans_owned_files(self):
        code = body(builder.build(ROOT))
        status, output, calls, directories, _ = self.execute(code)
        self.assertEqual(status, 0, output)
        self.assertEqual(calls, [(ROOT / 'held_packet.py').read_bytes()])
        self.assertEqual(len(directories), 1)
        self.assertFalse(directories[0].exists())
        record = json.loads(output.removeprefix('HELD_RUNTIME_PACKET '))
        self.assertIs(record['fixture_only'], True)
        self.assertIs(record['transport_temporary_files_removed'], True)
        self.assertEqual(record['executed_packet_sha256'], hashlib.sha256(calls[0]).hexdigest())

    def test_private_capture_rereads_stay_within_the_packet_byte_budget(self):
        code = body(builder.build(ROOT))
        original_open = Path.open
        reads = []
        owner = self
        class GuardedStream:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): return self.stream.__exit__(*args)
            def read(self, size=-1):
                owner.assertTrue(0 < size <= 32769, 'unbounded private packet reread')
                reads.append(size)
                return self.stream.read(size)
        def open_source(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            mode = args[0] if args else kwargs.get('mode', 'r')
            return GuardedStream(stream) if mode == 'rb' else stream
        with patch.object(Path, 'open', new=open_source):
            status, output, _, directories, _ = self.execute(code)
        self.assertEqual(status, 0, output)
        self.assertEqual(len(reads), 4)
        self.assertFalse(directories[0].exists())

    def test_self_consistent_changed_runner_refuses_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'unreviewed-runner-executed'
            changed = ("from pathlib import Path\nPath(" + repr(str(marker)) + ").touch()\n"
                       "def observe(*_): return {'fixture_only': True}\n").encode()
            def edit(rows):
                for index, row in enumerate(rows):
                    if row[0] == 'held_packet.py':
                        rows[index] = (row[0], hashlib.sha256(changed).hexdigest(),
                                       base64.b64encode(zlib.compress(changed)).decode())
            code = change_rows(builder.build(ROOT), edit)
            status, output, calls, _, _ = self.execute(code, real_runner=True)
            self.assertEqual(status, 1, output)
            self.assertEqual(output, 'HELD_RUNTIME_REFUSED no completion observation emitted\n')
            self.assertEqual(calls, [])
            self.assertFalse(marker.exists())

    def test_observation_has_real_seventy_five_second_alarm(self):
        def observer(*_):
            remaining, interval = signal.getitimer(signal.ITIMER_REAL)
            self.assertTrue(0 < remaining <= 75, 'observation exceeds documented 75-second deadline')
            self.assertEqual(interval, 0)
            return {'fixture_only': True}
        status, output, _, directories, _ = self.execute(body(builder.build(ROOT)), observer)
        self.assertEqual(status, 0, output)
        self.assertFalse(directories[0].exists())

    def test_actual_deadline_exception_refuses_and_cleans(self):
        def observer(*_):
            signal.raise_signal(signal.SIGALRM)
            self.fail('Deadline signal did not interrupt the observer')
        status, output, _, directories, _ = self.execute(body(builder.build(ROOT)), observer)
        self.assertEqual(status, 1, output)
        self.assertEqual(output, 'HELD_RUNTIME_REFUSED no completion observation emitted\n')
        self.assertFalse(directories[0].exists())

    def test_bad_row_shapes_and_payloads_refuse_before_compile(self):
        def duplicate(rows): rows[-1] = rows[0]
        def unknown(rows): rows[-1] = ('unknown.py', rows[-1][1], rows[-1][2])
        def changed_digest(rows): rows[-1] = (rows[-1][0], '0' * 64, rows[-1][2])
        def oversized(rows):
            rows[-1] = (rows[-1][0], rows[-1][1], base64.b64encode(zlib.compress(b'x' * 32769)).decode())
        def trailing(rows):
            value = base64.b64decode(rows[-1][2]) + b'trailing'
            rows[-1] = (rows[-1][0], rows[-1][1], base64.b64encode(value).decode())
        for edit in (duplicate, unknown, changed_digest, oversized, trailing):
            with self.subTest(edit=edit.__name__):
                status, output, calls, _, _ = self.execute(change_rows(builder.build(ROOT), edit))
                self.assertEqual(status, 1, output)
                self.assertEqual(output, 'HELD_RUNTIME_REFUSED no completion observation emitted\n')
                self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
