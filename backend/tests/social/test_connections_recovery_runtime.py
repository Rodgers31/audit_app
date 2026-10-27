"""Run real recovery sources on the selected interpreter, without ORM startup.

Only ORM/Pydantic initialization is bypassed. The shared error/canonical JSON
function bodies are extracted and executed; crypto and recovery modules are
imported unchanged, with real cryptography and filesystem operations.
"""
from pathlib import Path
import subprocess
import os
import sys

import pytest

PROBE = r'''
import ast
import importlib
import json
from pathlib import Path
import sys
import types
def require(condition, message):
    if not condition:
        raise RuntimeError(message)
backend = Path(sys.argv[1])
for name, directory in [('social', backend / 'social'), ('social.connections', backend / 'social' / 'connections'), ('scripts', backend / 'scripts')]:
    module = types.ModuleType(name); module.__path__ = [str(directory)]; sys.modules[name] = module
for name, file, target in [('social.service', 'service.py', 'SocialError'), ('social.contracts', 'contracts.py', 'canonical_json')]:
    source_path = (backend / 'social' / file).resolve()
    require(source_path.is_file() and source_path.parent == (backend / 'social').resolve(), 'recovery source path mismatch')
    source = ast.parse(source_path.read_text(), filename=str(source_path))
    definition = next(n for n in source.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name == target)
    module = types.ModuleType(name)
    module.__dict__.update(json=json, Any=object, BaseModel=type('UnusedModel', (), {}))
    compiled = compile(ast.Module(body=[definition], type_ignores=[]), str(source_path), 'exec')
    require(compiled.co_filename == str(source_path), 'compiled source identity mismatch')
    exec(compiled, module.__dict__)
    extracted = module.__dict__[target]
    code = extracted.__init__.__code__ if isinstance(extracted, type) else extracted.__code__
    require(code.co_filename == str(source_path), 'extracted source identity mismatch')
    sys.modules[name] = module
recovery = importlib.import_module('social.connections.recovery')
script = importlib.import_module('scripts.social_meta_recovery')
result = script.fixture_drill()
require(result['envelopes_decrypted'] == result['purposes_verified'] == 4, 'recovery envelope count mismatch')
require(result['negative_controls_rejected'] == 4, 'recovery negative control count mismatch')
require(result['production_authorized'] is result['digest_keys_verified'] is False, 'recovery authorization mismatch')
try:
    recovery.parse_keyring(b'{"secret":"inert"')
except recovery.RecoveryError as error:
    require(error.__context__ is error.__cause__ is None, 'recovery exception context leaked')
else:
    raise AssertionError('Malformed recovery accepted')
print('recovery-runtime-ok')
'''


@pytest.mark.parametrize("optimized", [False, True])
def test_recovery_sources_execute_on_selected_interpreter_without_orm(optimized):
    backend = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, '-B', '-c', PROBE, str(backend)],
                            capture_output=True, text=True, timeout=10,
                            env=dict(os.environ, PYTHONOPTIMIZE='1' if optimized else '0'))
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'recovery-runtime-ok\n'
    assert result.stderr == ''


@pytest.mark.parametrize("optimized", [False, True])
def test_recovery_runtime_refuses_a_synthetic_source_filename(optimized):
    backend = Path(__file__).resolve().parents[2]
    # Execute the same extracted real definitions with the historical coverage
    # attribution defect. The identity guard must fail before recovery runs.
    incorrect = PROBE.replace("str(source_path), 'exec')", "'contracts.py', 'exec')")
    assert incorrect != PROBE
    result = subprocess.run([sys.executable, '-B', '-c', incorrect, str(backend)],
                            capture_output=True, text=True, timeout=10,
                            env=dict(os.environ, PYTHONOPTIMIZE='1' if optimized else '0'))
    assert result.returncode != 0
    assert 'RuntimeError: compiled source identity mismatch' in result.stderr
    assert 'recovery-runtime-ok' not in result.stdout
