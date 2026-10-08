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
    source = ast.parse((backend / 'social' / file).read_text())
    definition = next(n for n in source.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == target)
    module = types.ModuleType(name)
    module.__dict__.update(json=json, Any=object, BaseModel=type('UnusedModel', (), {}))
    exec(compile(ast.Module(body=[definition], type_ignores=[]), file, 'exec'), module.__dict__)
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
