"""Original execution receipt path binding; these are local inert pytest runs."""
import json
from pathlib import Path
import re

import pytest
import common
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


def test_rehash_refuses_growth_without_consuming_beyond_the_declared_cap(tmp_path,monkeypatch):
    maximum=16
    payload=b'bound-original'
    path=tmp_path/'receipt.json'
    path.write_bytes(payload)
    evidence=common.BoundEvidence(maximum_bytes=maximum)
    evidence.__enter__()
    try:
        assert evidence.read(path)==payload
        target_fd=evidence.files[0][0]
        original_read=common.os.read
        observed={'grew':False,'consumed':0}
        def grow_after_precheck(fd,count):
            # The helper has already compared fstat/path identities. Grow the
            # actual same regular file at its first subsequent descriptor read.
            if fd==target_fd and not observed['grew']:
                with path.open('ab')as stream:stream.write(b'x'*4096)
                observed['grew']=True
            result=original_read(fd,count)
            if fd==target_fd:observed['consumed']+=len(result)
            return result
        with monkeypatch.context()as patch:
            patch.setattr(common.os,'read',grow_after_precheck)
            with pytest.raises(common.Refusal,match='changed|binding|byte|ceiling|limit'):
                evidence.check()
        assert observed['grew']is True
        assert path.stat().st_size==len(payload)+4096
        # One sentinel byte beyond the cap is allowed for early overflow proof;
        # consuming the complete grown file before refusing is the regression.
        assert observed['consumed']<=maximum+1,observed
    finally:
        # The explicit failed check has already run. Close the retained owned
        # descriptors without retrying the intentionally malformed original.
        evidence.__exit__(RuntimeError,RuntimeError('intentional invalid original'),None)


def test_real_verifier_refuses_parent_alias_installed_during_final_rehash(tmp_path,monkeypatch):
    repo,expected=make_repo(tmp_path,'def test_probe(): pass\n')
    output=tmp_path/'original'
    result=record.run(repo,output,expected,['test_probe.py'],timeout=15)
    assert result['verdict']=='LOCAL_CONTROLS_PASSED',result['failures']
    assert verify.validate(output/'execution.json',repo)['verdict']=='LOCAL_CONTROLS_PASSED'
    moved=tmp_path/'moved-original'
    real_check=common.BoundEvidence.check
    real_read=common.os.read
    state={'checking':False,'substituted':False}
    def checker(self):
        state['checking']=True
        try:return real_check(self)
        finally:state['checking']=False
    def substitute_at_consumption(fd,count):
        if state['checking']and not state['substituted']:
            output.rename(moved)
            output.symlink_to(moved,target_is_directory=True)
            state['substituted']=True
        return real_read(fd,count)
    accepted=None
    refusal=None
    try:
        with monkeypatch.context()as patch:
            patch.setattr(common.BoundEvidence,'check',checker)
            patch.setattr(common.os,'read',substitute_at_consumption)
            try:accepted=verify.validate(output/'execution.json',repo)
            except common.Refusal as exc:refusal=exc
        assert state['substituted']is True,'final rehash boundary did not run'
        assert output.is_symlink(),'actual late path substitution did not occur'
        assert accepted is None,{'accepted_verdict':accepted['verdict'],'parent_is_symlink':output.is_symlink()}
        assert refusal is not None and re.search('binding|directory|substitut|changed|symlink',str(refusal)),refusal
    finally:
        if output.is_symlink():output.unlink()
        if moved.exists()and not output.exists():moved.rename(output)
