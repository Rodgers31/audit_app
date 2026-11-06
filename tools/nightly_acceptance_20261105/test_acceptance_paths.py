"""Original execution receipt path binding; these are local inert pytest runs."""
import json
from pathlib import Path

import pytest
from common import Refusal
import record
import verify
from test_controls import make_repo


def recorded(tmp_path):
    repo, expected = make_repo(tmp_path, 'def test_probe(): pass\n')
    output = tmp_path / 'original'
    result = record.run(repo, output, expected, ['test_probe.py'], timeout=15)
    assert result['verdict'] == 'LOCAL_CONTROLS_PASSED', result['failures']
    return output, repo


def test_receipt_through_symlink_parent_refuses_before_read(tmp_path, monkeypatch):
    original = tmp_path / 'original'; original.mkdir()
    (original / 'execution.json').write_text('{}')
    alias = tmp_path / 'alias'; alias.symlink_to(original, target_is_directory=True)
    touched = []
    def read(path):
        touched.append(path)
        raise AssertionError('symlink parent was read')
    monkeypatch.setattr(verify, 'read_json', read)
    with pytest.raises(Refusal, match='[Ss]ymlink|original|alias'):
        verify.validate(alias / 'execution.json')
    assert touched == []


def test_unchanged_legitimate_retained_receipt_verifies(tmp_path):
    original, repo = recorded(tmp_path)
    assert verify.validate(original / 'execution.json', repo)['verdict'] == 'LOCAL_CONTROLS_PASSED'


def test_parent_replacement_during_consumption_refuses(tmp_path, monkeypatch):
    original, repo = recorded(tmp_path)
    old = tmp_path / 'moved'
    actual = record.validate_outcomes
    def replace(*args, **kwargs):
        result = actual(*args, **kwargs)
        original.rename(old)
        original.symlink_to(old, target_is_directory=True)
        return result
    monkeypatch.setattr(verify, 'validate_outcomes', replace)
    with pytest.raises(Refusal, match='[Ss]ymlink|changed|substitut|binding'):
        verify.validate(original / 'execution.json', repo)


def test_artifact_replacement_during_consumption_refuses(tmp_path, monkeypatch):
    original, repo = recorded(tmp_path)
    actual = record.validate_outcomes
    def replace(*args, **kwargs):
        result = actual(*args, **kwargs)
        path = original / 'stdout.log'
        body = path.read_bytes(); path.unlink(); path.write_bytes(body)
        return result
    monkeypatch.setattr(verify, 'validate_outcomes', replace)
    with pytest.raises(Refusal, match='changed|substitut|binding'):
        verify.validate(original / 'execution.json', repo)


def test_hardlink_artifact_alias_refuses(tmp_path):
    import os
    original, repo = recorded(tmp_path)
    os.link(original / 'stdout.log', tmp_path / 'stdout-alias')
    with pytest.raises(Refusal, match='link|alias'):
        verify.validate(original / 'execution.json', repo)
