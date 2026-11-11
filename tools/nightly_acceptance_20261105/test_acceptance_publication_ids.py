"""Publication-source ID unit-projection adversary from independent Spec review.

The owned PG connection, source/job/extraction rows, native publication producer,
actual publication authority reader and actual semantic importer execute in this control. Only unrelated catalog/current-run/refresh
checks are explicit doubles. This is not full operational/source acceptance.
"""
import copy
from pathlib import Path

import pytest

from common import Refusal, canonical, sha256
from acceptance_backend_config import PG_URL, PLUGINS
import acceptance_semantic
import operational
from test_acceptance_authority import owned_database
from test_acceptance_snapshot import native_fixture


def test_boolean_publication_source_id_refuses_before_authority_projection(
        owned_database, tmp_path, monkeypatch):
    # A fresh owned schema makes this a real qualified source with ID 1.
    # native_fixture uses the real producer and retained PDF/capture contracts.
    job_id, record_id, source_id, original, retained = native_fixture(owned_database, tmp_path)
    assert type(source_id) is int and source_id == 1

    run_binding = {'commit': 'a' * 40, 'run_id': 101, 'attempt': 1}
    projected_current = {
        'scope': 'UNIT_PROJECTION_CURRENT_RUN_DOUBLE',
        'report': {'jobs': [{'domain': 'audits', 'job_id': job_id}]},
    }
    monkeypatch.setattr(acceptance_semantic, 'observe_catalog',
                        lambda *args, **kwargs: {'scope': 'UNIT_PROJECTION_CATALOG_DOUBLE'})
    monkeypatch.setattr(acceptance_semantic, 'observe_current_run',
                        lambda *args, **kwargs: copy.deepcopy(projected_current))
    monkeypatch.setattr(acceptance_semantic, 'verify_capture',
                        lambda *args, **kwargs: {'scope': 'UNIT_PROJECTION_REFRESH_DOUBLE'})

    # Do not replace observe_oag_report or owned_reader: they must validate the
    # real current source, native receipt, job, snapshot, PDF and retained bytes.
    def reference(path):
        path = Path(path)
        return {'path': path.relative_to(tmp_path).as_posix(),
                'sha256': sha256(path), 'size': path.stat().st_size}

    def put(name, value):
        path = tmp_path / name
        with path.open('xb') as stream:
            stream.write(canonical(value))
        return reference(path)

    value = {
        'schema': 'nightly-semantic-local-input-v1',
        'kind': 'full15', 'binding': run_binding,
        'plan': put('projection-plan.json', {'scope': 'UNIT_PROJECTION_PLAN'}),
        'context': put('projection-context.json', {
            'source_sha': run_binding['commit'], 'run_id': '101', 'run_attempt': '1'}),
        'current_report': put('projection-current.json', projected_current),
        'pg_schema': owned_database.info_acceptance['schema'],
        'refresh': put('projection-refresh.json', {'scope': 'UNIT_PROJECTION_REFRESH_INPUT'}),
        'census': put('projection-census.json', {'scope': 'UNIT_PROJECTION_CENSUS_INPUT'}),
        'oag': [{'scope': 'publication', 'job_id': job_id, 'source_id': source_id,
                 'record_id': record_id, 'original': reference(original), 'retained': reference(retained)}],
        'fiscal': None,
    }
    config = {'schema': 'nightly-backend-config-v1', 'plugins': list(PLUGINS),
              'pg_url': PG_URL, 'fixture_token': owned_database.info_acceptance['token'],
              'original_family': 'none'}
    put('projection-backend.json', config)
    key = tmp_path / 'projection-test-key'
    with key.open('xb') as stream:
        stream.write(b'inert-projection-signing-key-20261105')
    positive = tmp_path / 'projection-positive.json'
    put(positive.name, value)
    kwargs = {'backend_config': tmp_path / 'projection-backend.json', 'signing_key_file': key}

    observed = operational.observe_local(positive, **kwargs)
    actual_publication = observed['oag'][0]
    assert actual_publication['source_document_id'] == 1
    assert actual_publication['publication']['report']['source_document_id'] == 1
    assert actual_publication['publication']['report']['publisher'] == 'Office of the Auditor-General'
    assert observed['production_accepted'] is False

    # Change exactly the declared source identity. All genuine publication,
    # original PDF, job and retained-source evidence remains unchanged.
    bad = copy.deepcopy(value)
    bad['oag'][0]['source_id'] = True
    hostile = tmp_path / 'projection-boolean-source.json'
    put(hostile.name, bad)
    with pytest.raises(Refusal, match='integer|source'):
        operational.observe_local(hostile, **kwargs)
