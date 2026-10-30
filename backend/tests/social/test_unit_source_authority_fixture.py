"""The policy unit authority cannot escape its named synthetic-source scope."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from social.service import SocialError
from social.generation.worker_authority import verify_worker_authority as production_verify
from test_domain_support import db
from test_generation import observation
from unit_source_authority_fixture import (UnitSourceAuthority,
    install_unit_source_authority, register_unit_observation)


def test_only_registered_source_hash_in_owned_engine_receives_unit_authority(db):
    port = UnitSourceAuthority(db.get_bind())
    value = observation()
    source = value.model_dump(mode='json')
    assert port.capture(db, source) is None
    port.register(value)
    witness = port.capture(db, source)
    assert witness['UNIT_AUTHORITY_ONLY'] is True
    port.verify(db, source, witness)
    with pytest.raises(SocialError, match='SOURCE_REVIEW_REQUIRED'):
        production_verify(db, source, witness)


def test_source_mutation_cannot_reuse_an_issued_unit_marker(db):
    port = UnitSourceAuthority(db.get_bind())
    value = observation()
    port.register(value)
    source = value.model_dump(mode='json')
    witness = port.capture(db, source)
    changed = deepcopy(source)
    changed['facts'][0]['value'] = '999'
    assert port.capture(db, changed) is None
    with pytest.raises(SocialError, match='SOURCE_REVIEW_REQUIRED'):
        port.verify(db, changed, witness)


def test_owned_connection_session_keeps_the_exact_engine_scope(db):
    port = UnitSourceAuthority(db.get_bind())
    value = observation()
    port.register(value)
    source = value.model_dump(mode='json')
    witness = port.capture(db, source)
    with db.get_bind().connect() as connection:
        with Session(bind=connection) as wrapped:
            port.verify(wrapped, source, witness)
            assert port.capture(wrapped, source) == witness


def test_unit_marker_cannot_cross_an_engine_or_owner(db):
    port = UnitSourceAuthority(db.get_bind())
    value = observation()
    port.register(value)
    source = value.model_dump(mode='json')
    witness = port.capture(db, source)
    foreign = create_engine('sqlite://')
    try:
        with Session(foreign) as other:
            assert port.capture(other, source) is None
            with pytest.raises(SocialError, match='SOURCE_REVIEW_REQUIRED'):
                port.verify(other, source, witness)
    finally:
        foreign.dispose()
    forged = {**witness, 'owner': 'another-unit-owner'}
    with pytest.raises(SocialError, match='SOURCE_REVIEW_REQUIRED'):
        port.verify(db, source, forged)


@pytest.mark.parametrize('change', [
    {'UNIT_AUTHORITY_ONLY': 1}, {'owner': None}, {'source_hash': '0' * 64},
    {'version': 1}, {'unexpected': True},
])
def test_forged_unit_marker_never_becomes_authority(db, change):
    port = UnitSourceAuthority(db.get_bind())
    value = observation()
    port.register(value)
    source = value.model_dump(mode='json')
    witness = {**port.capture(db, source), **change}
    with pytest.raises(SocialError, match='SOURCE_REVIEW_REQUIRED'):
        port.verify(db, source, witness)


@pytest.mark.parametrize('change', [
    {'fixture': True}, {'committed': False}, {'publishable': False},
    {'quarantined': True}, {'source_key': 'budget_lines:1:actual_spent'},
    {'ingestion_id': '42'},
])
def test_bad_or_production_source_cannot_enter_the_unit_port(db, change):
    port = UnitSourceAuthority(db.get_bind())
    with pytest.raises(ValueError, match='declared synthetic'):
        port.register(observation(**change))


def test_unit_port_is_not_installable_on_a_postgres_engine():
    with pytest.raises(ValueError, match='SQLite-only'):
        UnitSourceAuthority(SimpleNamespace(dialect=SimpleNamespace(name='postgresql')))


def test_no_explicit_unit_opt_in_leaves_real_authority_unchanged(db):
    value = observation()
    register_unit_observation(db, value)
    with pytest.raises(SocialError, match='SOURCE_REVIEW_REQUIRED'):
        production_verify(db, value.model_dump(mode='json'), None)


def test_named_opt_in_restores_production_functions_after_scope(db, monkeypatch):
    import social.generation.worker_authority as authority
    before_capture, before_verify = authority.capture_worker_authority, authority.verify_worker_authority
    with monkeypatch.context() as scoped:
        port = install_unit_source_authority(scoped, db)
        value = register_unit_observation(db, observation())
        source = value.model_dump(mode='json')
        witness = authority.capture_worker_authority(db, source)
        authority.verify_worker_authority(db, source, witness)
        assert port.engine is db.get_bind()
    assert authority.capture_worker_authority is before_capture
    assert authority.verify_worker_authority is before_verify
    assert authority.capture_worker_authority(db, source) is None
    with pytest.raises(SocialError, match='SOURCE_REVIEW_REQUIRED'):
        authority.verify_worker_authority(db, source, witness)
