"""Actual subprocess/metadata boundaries; toy Git sources and inert test bodies."""
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

from common import Refusal, loads, publish
import record
import runtime


@pytest.mark.parametrize('raw', ['', '{} trailing', '{"x":1,"x":2}', 'NaN', 'Infinity', '-Infinity', '1e999'])
def test_strict_json_refuses(raw):
    with pytest.raises(Refusal):
        loads(raw)


@pytest.mark.parametrize('value', [None, '', [], {}, True, 0, float('nan')])
def test_empty_or_wrong_case_inventory_refuses(tmp_path, value):
    with pytest.raises(Refusal):
        record.validate_outcomes({'exitstatus': 0, 'reports': []}, tmp_path / 'absent', value, 0)


@pytest.mark.parametrize('value', [None, False, True, -1, 0.0, float('inf'), '0'])
def test_exit_primitive_refuses(tmp_path, value):
    with pytest.raises(Refusal):
        record.validate_outcomes({}, tmp_path / 'absent', ['test_x.py::test_x'], value)


def make_repo(tmp_path, body):
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'test_probe.py').write_text(body)
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    subprocess.run(['git', '-C', str(repo), 'add', 'test_probe.py'], check=True)
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Inert Fixture', '-c',
                    'user.email=inert@example.invalid', 'commit', '-qm', 'fixture'], check=True)
    expected = tmp_path / 'expected.json'
    expected.write_text(json.dumps(['test_probe.py::test_probe']))
    return repo, expected


@pytest.mark.parametrize('body,passes', [
    ('def test_probe():\n    assert True\n', True),
    ('def test_probe():\n    assert False\n', False),
    ('import pytest\n@pytest.mark.skip(reason="inert")\ndef test_probe(): pass\n', False),
    ('import pytest\n@pytest.mark.xfail(strict=False)\ndef test_probe(): pass\n', False),
    ('import pytest\n@pytest.mark.xfail(strict=True)\ndef test_probe(): assert False\n', False),
    ('raise RuntimeError("collection broke")\n', False),
])
def test_recorder_real_subprocess_outcomes(tmp_path, body, passes):
    repo, expected = make_repo(tmp_path, body)
    result = record.run(repo, tmp_path / 'receipt', expected, ['test_probe.py'], timeout=15)
    assert (result['verdict'] == 'LOCAL_CONTROLS_PASSED') is passes, result['failures']
    assert result['cleanup']['group_absent'] is True
    assert result['cleanup']['leader_reaped'] is True
    assert record.read_json(tmp_path / 'receipt/execution.json') == result


def test_recorder_drops_ambient_secrets(tmp_path, monkeypatch):
    repo, expected = make_repo(tmp_path, 'import os\ndef test_probe():\n'
                              '    assert "TOY_PROVIDER_TOKEN" not in os.environ\n'
                              '    assert "DATABASE_URL" not in os.environ\n')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://toy:toy@invalid.invalid/toy')
    monkeypatch.setenv('TOY_PROVIDER_TOKEN', 'toy-secret')
    result = record.run(repo, tmp_path / 'receipt', expected, ['test_probe.py'], timeout=15)
    assert result['verdict'] == 'LOCAL_CONTROLS_PASSED', result['failures']
    assert 'toy-secret' not in (tmp_path / 'receipt/execution.json').read_text()


def test_source_mutation_is_failure_even_with_passing_child(tmp_path):
    repo, expected = make_repo(tmp_path, 'from pathlib import Path\ndef test_probe():\n'
                              '    Path("untracked-input").write_text("changed")\n')
    result = record.run(repo, tmp_path / 'receipt', expected, ['test_probe.py'], timeout=15)
    assert result['child_exit'] == 0
    assert result['verdict'] == 'FAILED'
    assert 'consumed source/corpus changed' in result['failures']


def test_missing_selector_is_not_passing(tmp_path):
    repo, expected = make_repo(tmp_path, 'def test_probe(): pass\n')
    result = record.run(repo, tmp_path / 'receipt', expected, ['missing.py'], timeout=15)
    assert result['verdict'] == 'FAILED'
    assert not result['executed']


def test_timeout_reaps_owned_group(tmp_path):
    repo, expected = make_repo(tmp_path, 'import time\ndef test_probe(): time.sleep(30)\n')
    result = record.run(repo, tmp_path / 'receipt', expected, ['test_probe.py'], timeout=1)
    assert result['verdict'] == 'FAILED'
    assert 'child timed out' in result['failures']
    assert result['cleanup']['group_absent'] is True


def test_output_cannot_overwrite_source_or_existing_receipt(tmp_path):
    repo, expected = make_repo(tmp_path, 'def test_probe(): pass\n')
    before = (repo / 'test_probe.py').read_bytes()
    for output in (repo / 'test_probe.py', repo / 'receipt', expected):
        with pytest.raises(Refusal):
            record.run(repo, output, expected, ['test_probe.py'])
    assert (repo / 'test_probe.py').read_bytes() == before
    output = tmp_path / 'existing'
    output.mkdir()
    with pytest.raises(Refusal):
        record.run(repo, output, expected, ['test_probe.py'])


def test_duplicate_phase_and_missing_phase_refuse(tmp_path):
    case = 'test_probe.py::test_probe'
    report = {'exitstatus': 0, 'reports': [dict(nodeid=case, phase=p, outcome='passed', wasxfail=None)
                                         for p in ('setup', 'call', 'teardown')]}
    xml = tmp_path / 'junit.xml'
    xml.write_text('<testsuites><testsuite><testcase classname="test_probe" name="test_probe"/>'
                   '</testsuite></testsuites>')
    assert record.validate_outcomes(report, xml, [case], 0) == [case]
    bad = copy.deepcopy(report)
    bad['reports'].append(bad['reports'][0])
    with pytest.raises(Refusal):
        record.validate_outcomes(bad, xml, [case], 0)
    report['reports'].pop()
    with pytest.raises(Refusal):
        record.validate_outcomes(report, xml, [case], 0)


def test_runtime_complete_lock_and_manifest_binding():
    lock = runtime.load_lock()
    assert len(lock['packages']) == 86
    assert {p['name']: p['version'] for p in lock['packages']}['sqlalchemy'] == '2.0.57'
    assert {p['name']: p['version'] for p in lock['packages']}['pandas'] == '3.1.1'


@pytest.mark.parametrize('mutation', ['empty', 'duplicate', 'bool-version', 'unknown', 'bad-url'])
def test_runtime_lock_malformed_refuses(tmp_path, mutation):
    lock = runtime.read_json(runtime.LOCK)
    if mutation == 'empty': lock['packages'] = []
    if mutation == 'duplicate': lock['packages'].append(lock['packages'][0])
    if mutation == 'bool-version': lock['packages'][0]['version'] = True
    if mutation == 'unknown': lock['schema'] = 'future'
    if mutation == 'bad-url': lock['packages'][0]['url'] = 'https://invalid.invalid/a.whl'
    path = tmp_path / 'lock.json'
    path.write_text(json.dumps(lock))
    with pytest.raises(Refusal): runtime.load_lock(path)


def test_wheelhouse_missing_or_extra_refuses(tmp_path):
    with pytest.raises(Refusal): runtime.wheels_verified(runtime.load_lock(), tmp_path)


def test_readback_is_strict_and_exclusive(tmp_path):
    path = tmp_path / 'receipt.json'
    publish(path, {'exit': 0, 'ok': False})
    assert path.read_text() == '{"exit":0,"ok":false}\n'
    with pytest.raises(FileExistsError): publish(path, {'exit': 1})


def test_direct_runtime_boundaries_cannot_accept_unqualified_lock(tmp_path):
    import platform
    with pytest.raises(Refusal):
        runtime.wheels_verified({'packages': []}, tmp_path)
    with pytest.raises(Refusal):
        runtime.target_verified(dict(python=platform.python_version(), system=platform.system(),
                                     machine=platform.machine()))


def test_unrelated_junit_identity_refuses(tmp_path):
    node = 'test_good.py::test_good'
    phases = {'exitstatus': 0, 'reports': [dict(nodeid=node, phase=p, outcome='passed', wasxfail=None)
                                         for p in ('setup', 'call', 'teardown')]}
    junit = tmp_path / 'junit.xml'
    junit.write_text('<testsuites><testsuite><testcase classname="other" name="other"/></testsuite></testsuites>')
    with pytest.raises(Refusal): record.validate_outcomes(phases, junit, [node], 0)


def test_ledger_output_inside_consumed_source_refuses(tmp_path):
    import ledger
    repo, _ = make_repo(tmp_path, 'def test_probe(): pass\n')
    with pytest.raises(Refusal): ledger.prepare(repo, repo / 'ledger.json')


def test_missing_installed_record_entry_refuses(tmp_path, monkeypatch):
    import importlib.metadata
    distroot = tmp_path / 'dist'
    metadata = distroot / 'inert_probe-1.0.dist-info'
    metadata.mkdir(parents=True)
    (metadata / 'METADATA').write_text('Metadata-Version: 2.1\nName: inert-probe\nVersion: 1.0\n')
    (metadata / 'RECORD').write_text('inert_probe-1.0.dist-info/METADATA,,\nmissing_extension.so,,\ninert_probe-1.0.dist-info/RECORD,,\n')
    distributions = [importlib.metadata.PathDistribution(metadata)]
    assert 'missing_extension.so,,' in distributions[0].read_text('RECORD').splitlines()
    monkeypatch.setattr(importlib.metadata, 'distributions', lambda: distributions)
    with pytest.raises(Refusal, match='installed RECORD file absent'): runtime.package_inventory()


@pytest.mark.parametrize('attribute,value', [('errors','1'),('errors','NaN'),('skipped','false'),
                                             ('failures','-1'),('tests','2'),('time','NaN')])
def test_malformed_junit_counters_refuse(tmp_path, attribute, value):
    node = 'test_x.py::test_x'
    phases = {'exitstatus': 0, 'reports': [dict(nodeid=node, phase=p, outcome='passed', wasxfail=None)
                                         for p in ('setup', 'call', 'teardown')]}
    junit = tmp_path / 'junit.xml'
    junit.write_text(f'<testsuites><testsuite {attribute}="{value}"><testcase classname="test_x" '
                     'name="test_x"/></testsuite></testsuites>')
    with pytest.raises(Refusal): record.validate_outcomes(phases, junit, [node], 0)


def test_partial_reviewed_lock_refuses(tmp_path):
    lock = runtime.read_json(runtime.LOCK)
    lock['packages'] = [r for r in lock['packages'] if r['name'] == 'pip']
    path = tmp_path / 'lock.json'; path.write_text(json.dumps(lock))
    with pytest.raises(Refusal): runtime.load_lock(path)


def test_special_consumed_file_refuses(tmp_path):
    (tmp_path / 'data').write_text('inert')
    os.mkfifo(tmp_path / 'fifo')
    with pytest.raises(Refusal): record.inventory(tmp_path)


def test_installer_symlink_ancestor_refuses_before_mutation(tmp_path, monkeypatch):
    source = tmp_path / 'source'; source.mkdir()
    alias = tmp_path / 'alias'; alias.symlink_to(source, target_is_directory=True)
    monkeypatch.setattr(runtime, 'target_verified', lambda lock: None)
    monkeypatch.setattr(runtime, 'wheels_verified', lambda lock, wheels: None)
    with pytest.raises(Refusal): runtime.install(runtime.LOCK, tmp_path, alias / 'venv')
    assert not (source / 'venv').exists()


@pytest.mark.parametrize('field,bad', [('environment',False),('runtime',True),('argv',[]),
                                      ('generated_at','2020-01-01T00:00:00+00:00')])
def test_execution_readback_tampering_refuses(tmp_path, field, bad):
    import verify
    repo, expected = make_repo(tmp_path, 'def test_probe(): pass\n')
    output = tmp_path / 'receipt'
    result = record.run(repo, output, expected, ['test_probe.py'], timeout=15)
    assert result['verdict'] == 'LOCAL_CONTROLS_PASSED', result['failures']
    verify.validate(output / 'execution.json', repo)
    result[field] = bad
    (output / 'execution.json').write_text(json.dumps(result))
    with pytest.raises((Refusal, ValueError)): verify.validate(output / 'execution.json', repo)


def test_prepared_ledger_strict_source_time_and_false_acceptance(tmp_path):
    import ledger
    repo, expected = make_repo(tmp_path, 'def test_probe(): pass\n')
    path = tmp_path / 'ledger.json'
    original = ledger.prepare(repo, path)
    ledger.check_prepared(path)
    for field, bad in [('source', {'commit':'a'*40, 'tree':'b'*40}),
                       ('generated_at','2020-01-01'),('production_accepted',0)]:
        value = copy.deepcopy(original); value[field] = bad
        path.write_text(json.dumps(value))
        with pytest.raises((Refusal, ValueError)): ledger.check_prepared(path)


def test_qualification_profile_preserves_every_production_artifact():
    production = runtime.load_lock()
    qualification = runtime.load_lock(runtime.ROOT / 'backend/ingestion-qualification.lock.json')
    assert len(qualification['packages']) == 95
    rows = {r['name']: r for r in qualification['packages']}
    assert all(rows[row['name']] == row for row in production['packages'])


def test_inconsistent_junit_root_total_refuses(tmp_path):
    node = 'test_x.py::test_x'
    phases = {'exitstatus':0,'reports':[dict(nodeid=node,phase=p,outcome='passed',wasxfail=None)
                                      for p in ('setup','call','teardown')]}
    path=tmp_path/'junit.xml'
    path.write_text('<testsuites tests="999"><testsuite tests="1"><testcase classname="test_x" name="test_x"/></testsuite></testsuites>')
    with pytest.raises(Refusal): record.validate_outcomes(phases,path,[node],0)


@pytest.mark.parametrize('maximum',[float('inf'),float('nan'),True,0,-1,604801])
def test_direct_freshness_bounds_refuse(maximum):
    from verify import fresh_time
    with pytest.raises(Refusal): fresh_time('2020-01-01T00:00:00+00:00',maximum)


def test_suite_scope_error_refuses(tmp_path):
    node='test_good.py::test_good'
    phases={'exitstatus':0,'reports':[dict(nodeid=node,phase=p,outcome='passed',wasxfail=None)
                                     for p in ('setup','call','teardown')]}
    path=tmp_path/'junit.xml'
    path.write_text('<testsuites><testsuite><error message="fixture broke"/><testcase classname="test_good" name="test_good"/></testsuite></testsuites>')
    with pytest.raises(Refusal): record.validate_outcomes(phases,path,[node],0)


@pytest.mark.parametrize('name',['.','./input.txt','dir/../input.txt','/absolute'])
def test_source_inventory_alias_refuses(name):
    from verify import valid_source
    value=dict(commit='a'*40,tree='b'*40,status='',corpus={},files={name:dict(size=1,sha256='c'*64)})
    with pytest.raises(Refusal): valid_source(value)


def test_actual_locked_qualification_runtime_records_real_pytest(tmp_path):
    import verify
    repo,expected=make_repo(tmp_path,'def test_probe(): pass\n')
    output=tmp_path/'runtime-bound'
    lock=runtime.ROOT/'backend/ingestion-qualification.lock.json'
    result=record.run(repo,output,expected,['test_probe.py'],timeout=20,runtime_lock=lock)
    assert result['verdict']=='LOCAL_CONTROLS_PASSED',result['failures']
    assert len(result['runtime']['packages'])==95
    assert result['runtime']['qualification']=='PYTHON_ONLY_NATIVE_PENDING'
    assert verify.validate(output/'execution.json',repo)['runtime']==result['runtime']


def test_changed_consumed_bytecode_changes_actual_inventory(tmp_path,monkeypatch):
    import importlib.metadata
    import importlib.util
    import marshal
    import py_compile
    source=tmp_path/'inert_bytecode.py';source.write_text('VALUE="safe"\n')
    cache=Path(importlib.util.cache_from_source(str(source)))
    cache.parent.mkdir(exist_ok=True)
    py_compile.compile(str(source),cfile=str(cache),doraise=True)
    metadata=tmp_path/'inert_bytecode-1.0.dist-info';metadata.mkdir()
    (metadata/'METADATA').write_text('Metadata-Version: 2.1\nName: inert-bytecode\nVersion: 1.0\n')
    (metadata/'RECORD').write_text('inert_bytecode.py,,\n'+str(cache.relative_to(tmp_path))+',,\n'
                                 'inert_bytecode-1.0.dist-info/METADATA,,\ninert_bytecode-1.0.dist-info/RECORD,,\n')
    monkeypatch.setattr(importlib.metadata,'distributions',lambda:[importlib.metadata.PathDistribution(metadata)])
    before=runtime.package_inventory()
    cache.write_bytes(cache.read_bytes()[:16]+marshal.dumps(compile('VALUE="changed"\n',str(source),'exec')))
    after=runtime.package_inventory()
    assert before!=after
    spec=importlib.util.spec_from_file_location('inert_bytecode',source)
    loaded=importlib.util.module_from_spec(spec);spec.loader.exec_module(loaded)
    assert loaded.VALUE=='changed'


def test_actual_installed_payload_tampering_refuses_and_restores():
    import importlib.metadata
    lock=runtime.load_lock(runtime.ROOT/'backend/ingestion-qualification.lock.json')
    path=Path(importlib.metadata.distribution('fuzzywuzzy').locate_file('fuzzywuzzy/__init__.py'))
    original=path.read_bytes()
    try:
        path.write_bytes(original+b'\n# inert owned fixture mutation\n')
        with pytest.raises(Refusal,match='installed wheel payload differs'): runtime.payloads_verified(lock)
    finally:
        path.write_bytes(original)
    runtime.payloads_verified(lock)


def test_payload_direct_empty_lock_refuses():
    with pytest.raises(Refusal): runtime.payloads_verified({'packages':[]})


def test_actual_extra_registered_payload_refuses_and_restores():
    import importlib.metadata
    import sysconfig
    lock=runtime.load_lock(runtime.ROOT/'backend/ingestion-qualification.lock.json')
    distribution=importlib.metadata.distribution('fuzzywuzzy')
    site=Path(sysconfig.get_path('purelib'))
    extra=site/'unreviewed_inert_runtime.py'
    metadata=Path(distribution.locate_file('fuzzywuzzy-0.18.0.dist-info/RECORD'))
    original=metadata.read_bytes()
    try:
        extra.write_text('VALUE="inert unauthorized payload"\n')
        with metadata.open('a') as stream: stream.write('unreviewed_inert_runtime.py,,\n')
        with pytest.raises(Refusal,match='unreviewed payload'): runtime.payloads_verified(lock)
    finally:
        metadata.write_bytes(original)
        extra.unlink(missing_ok=True)
    runtime.payloads_verified(lock)


@pytest.mark.parametrize('script',['jp.py','pytest'])
def test_actual_script_interpreter_or_body_tampering_refuses_and_restores(script):
    lock=runtime.load_lock(runtime.ROOT/'backend/ingestion-qualification.lock.json')
    path=Path(sys.prefix)/'bin'/script
    original=path.read_bytes()
    try:
        path.write_bytes(b'#!/usr/bin/false\n'+original.split(b'\n',1)[1])
        with pytest.raises(Refusal): runtime.payloads_verified(lock)
    finally: path.write_bytes(original)
    runtime.payloads_verified(lock)


def test_actual_site_symlink_directory_refuses_and_cleans(tmp_path):
    import sysconfig
    lock=runtime.load_lock(runtime.ROOT/'backend/ingestion-qualification.lock.json')
    target=tmp_path/'inert_external_package';target.mkdir()
    (target/'__init__.py').write_text('VALUE="inert"\n')
    alias=Path(sysconfig.get_path('purelib'))/'unreviewed_inert_package'
    try:
        alias.symlink_to(target,target_is_directory=True)
        with pytest.raises(Refusal,match='site-package symlink'): runtime.payloads_verified(lock)
    finally: alias.unlink(missing_ok=True)
    assert not alias.exists()
    runtime.payloads_verified(lock)
