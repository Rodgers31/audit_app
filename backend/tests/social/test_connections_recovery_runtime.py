"""Run real recovery sources on the selected interpreter, without ORM startup.

Only ORM/Pydantic initialization is bypassed. The shared error/canonical JSON
function bodies are extracted and executed; crypto and recovery modules are
imported unchanged, with real cryptography and filesystem operations.
"""
from pathlib import Path
import subprocess
import sys

PROBE = r'''
import ast
import importlib
import json
from pathlib import Path
import sys
import types
backend = Path(sys.argv[1])
for name, directory in [('social', backend / 'social'), ('social.connections', backend / 'social' / 'connections'), ('scripts', backend / 'scripts')]:
    module = types.ModuleType(name); module.__path__ = [str(directory)]; sys.modules[name] = module
for name, file, target in [('social.service', 'service.py', 'SocialError'), ('social.contracts', 'contracts.py', 'canonical_json')]:
    source_path = (backend / 'social' / file).resolve()
    assert source_path.is_file() and source_path.parent == (backend / 'social').resolve()
    source = ast.parse(source_path.read_text(), filename=str(source_path))
    definition = next(n for n in source.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == target)
    module = types.ModuleType(name)
    module.__dict__.update(json=json, Any=object, BaseModel=type('UnusedModel', (), {}))
    compiled = compile(ast.Module(body=[definition], type_ignores=[]), str(source_path), 'exec')
    assert compiled.co_filename == str(source_path)
    exec(compiled, module.__dict__)
    extracted = module.__dict__[target]
    code = extracted.__init__.__code__ if isinstance(extracted, type) else extracted.__code__
    assert code.co_filename == str(source_path)
    sys.modules[name] = module
recovery = importlib.import_module('social.connections.recovery')
script = importlib.import_module('scripts.social_meta_recovery')
result = script.fixture_drill()
assert result['envelopes_decrypted'] == result['purposes_verified'] == 4
assert result['negative_controls_rejected'] == 4
assert result['production_authorized'] is result['digest_keys_verified'] is False
try:
    recovery.parse_keyring(b'{"secret":"inert"')
except recovery.RecoveryError as error:
    assert error.__context__ is error.__cause__ is None
else:
    raise AssertionError('Malformed recovery accepted')
print('recovery-runtime-ok')
'''


def test_recovery_sources_execute_on_selected_interpreter_without_orm():
    backend = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, '-B', '-c', PROBE, str(backend)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'recovery-runtime-ok\n'
    assert result.stderr == ''


def test_recovery_runtime_refuses_a_synthetic_source_filename():
    backend = Path(__file__).resolve().parents[2]
    # Execute the same extracted real definitions with the historical coverage
    # attribution defect. The identity guard must fail before recovery runs.
    incorrect = PROBE.replace("str(source_path), 'exec')", "'contracts.py', 'exec')")
    assert incorrect != PROBE
    result = subprocess.run([sys.executable, '-B', '-c', incorrect, str(backend)],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert 'AssertionError' in result.stderr
    assert 'recovery-runtime-ok' not in result.stdout
