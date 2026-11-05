"""Explicit local gate controls; require the reviewed official binary."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ENTRY = Path(__file__).with_name('semantic_gate.py')
spec = importlib.util.spec_from_file_location('nightly_semantic_gate', ENTRY)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.fixture
def official_binary():
    path = Path(os.environ['ACTIONLINT_BINARY'])
    checksum = os.environ['ACTIONLINT_SHA256']
    assert gate.digest(path) == checksum
    return path, checksum


@pytest.fixture
def source(tmp_path):
    root = tmp_path/'source'
    workflows = root/'.github/workflows'
    workflows.mkdir(parents=True)
    (workflows/'control.yml').write_text("name: local control\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo local\n")
    return root


def test_gate_accepts_real_official_semantics_and_binds_disk_receipt(tmp_path, source, official_binary):
    binary, checksum = official_binary
    receipt = tmp_path/'receipt.json'
    assert gate.run(source, binary, checksum, receipt) == 0
    record = json.loads(receipt.read_text())
    assert record['verdict'] == 'PASSED' and type(record['child_exit']) is int
    assert record['generator_sha256'] == gate.digest(ENTRY)
    assert set(record['target_files']) == {'.github/workflows/control.yml'}


def test_real_compiler_context_regression_is_rejected(source, official_binary):
    binary, checksum = official_binary
    path = source/'.github/workflows/control.yml'
    path.write_text(path.read_text().replace('      - run:', '      - env:\n          INVALID_STATUS: ${{ success() }}\n        run:'))
    assert gate.run(source, binary, checksum) == 1


@pytest.mark.parametrize('kind', ['absent','empty','bad_yaml','empty_choice','wrong_type'])
def test_actual_semantic_gate_refuses_bad_workflow_inventories(source, official_binary, kind):
    binary, checksum = official_binary
    path = source/'.github/workflows/control.yml'
    if kind == 'absent': path.unlink()
    elif kind == 'empty': path.write_text('')
    elif kind == 'bad_yaml': path.write_text('jobs: [bad\n')
    elif kind == 'wrong_type': path.write_text('jobs: 42\n')
    else: path.write_text("on:\n  workflow_dispatch:\n    inputs:\n      scope:\n        type: choice\n        options: ['']\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo local\n")
    if kind == 'absent':
        with pytest.raises(ValueError, match='inventory missing'): gate.run(source,binary,checksum)
    else:
        assert gate.run(source,binary,checksum) != 0


@pytest.mark.parametrize('value', ['',None,True,0,1.0,float('nan'),'z'*64,'0'*64])
def test_direct_binary_guard_has_no_cli_bypass(source, official_binary, value):
    binary, _ = official_binary
    with pytest.raises(ValueError): gate.run(source,binary,value)


def test_no_receipt_overwrite_or_source_injection(source, official_binary):
    binary, checksum = official_binary
    path = source/'.github/workflows/control.yml'
    before = path.read_bytes()
    with pytest.raises(ValueError, match='fresh and external'): gate.run(source,binary,checksum,path)
    assert path.read_bytes() == before


def test_cli_missing_binary_is_a_refusal_not_a_pass(source, tmp_path):
    result = subprocess.run([sys.executable,str(ENTRY),'--root',str(source),'--actionlint',str(tmp_path/'absent'),
        '--sha256','a'*64],capture_output=True,text=True,timeout=10)
    assert result.returncode == 2 and 'binary identity refused' in result.stderr


def test_linked_github_parent_does_not_escape_source_inventory(source, tmp_path, official_binary):
    binary, checksum = official_binary
    external = tmp_path/'external'; external.mkdir()
    (source/'.github').rename(external/'github')
    (source/'.github').symlink_to(external/'github',target_is_directory=True)
    with pytest.raises(ValueError,match='linked|escape'):
        gate.run(source,binary,checksum)


def test_analyzer_malfunction_is_uninterpretable_not_a_semantic_finding(source, tmp_path):
    # Inert analyzer-process double tests the recorder's outcome channel only.
    child = tmp_path/'analyzer'
    child.write_text('#!/bin/sh\nif [ "$1" = -version ]; then echo 1.7.12; exit 0; fi\nexit 2\n')
    child.chmod(0o755)
    receipt = tmp_path/'malfunction.json'
    assert gate.run(source,child,gate.digest(child),receipt) == 2
    assert json.loads(receipt.read_text())['verdict'] == 'UNINTERPRETABLE'


def test_generator_drift_cannot_be_relabelled_as_a_passing_execution(source,tmp_path,monkeypatch):
    # Owned imported gate copy and analyzer-process double exercise provenance,
    # without modifying candidate or claiming official compiler behavior.
    copied=tmp_path/'gate_copy.py';copied.write_bytes(ENTRY.read_bytes())
    loaded=importlib.util.spec_from_file_location('owned_gate_copy',copied)
    module=importlib.util.module_from_spec(loaded);loaded.loader.exec_module(module)
    original=module.digest(copied)
    child=tmp_path/'analyzer'
    child.write_text('#!/bin/sh\nif [ "$1" = -version ]; then echo 1.7.12; exit 0; fi\nprintf "\\n# concurrent owned edit\\n" >> "$OWNED_GATE_COPY"\nexit 0\n')
    child.chmod(0o755);monkeypatch.setenv('OWNED_GATE_COPY',str(copied))
    receipt=tmp_path/'drift.json'
    assert module.run(source,child,module.digest(child),receipt)==1
    record=json.loads(receipt.read_text())
    assert record['verdict']=='FAILED' and record['generator_sha256']==original
    assert record['generator_sha256_after']!=original
