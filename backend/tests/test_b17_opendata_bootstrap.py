"""Actual reference fence and initializer against the new native owner."""
import pytest
from sqlalchemy import text
import bootstrap
from seeding.exclusion import enter_domains, enter_domain, DomainOwnershipError
from test_b17_opendata_native import opendata_url, opendata_pg, query
from test_b17_opendata_writer import owned, counts


@pytest.mark.parametrize('retained', [False, True])
def test_actual_bootstrap_refuses_active_and_uncertain_opendata(opendata_url, monkeypatch, retained):
    with owned(opendata_url) as (engine, factory, execution, context):
        monkeypatch.setattr(bootstrap, 'SessionLocal', factory)
        def unexpected(*args):
            raise AssertionError('Bootstrap read/mutated reference input behind retained owner')
        monkeypatch.setattr(bootstrap, '_load_json', unexpected)
        if retained: execution.close()
        before = counts(engine)
        assert bootstrap.initialize_reference_data(force=True) is False
        assert counts(engine) == before
        assert query(engine, "SELECT id FROM seeding_domain_claims WHERE domain='opendata' AND released_at IS NULL")[0]['id'] == execution.identity


def test_bootstrap_group_fences_opendata_before_reference_effects(opendata_pg):
    _, factory, engine, _ = opendata_pg
    group=enter_domains(factory,bootstrap.BOOTSTRAP_EFFECT_DOMAINS,bootstrap.BOOTSTRAP_DOMAIN)
    try:
        assert group.continuous()
        held=query(engine,"SELECT domain FROM seeding_domain_claims WHERE released_at IS NULL ORDER BY domain")
        assert {r['domain'] for r in held} == set(bootstrap.BOOTSTRAP_EFFECT_DOMAINS)
        assert 'opendata' in {r['domain'] for r in held}
        with pytest.raises(DomainOwnershipError): enter_domain(factory,'opendata',False)
        assert not query(engine,'SELECT 1 FROM source_documents')
    finally: group.close()
    # Closing continuity is uncertainty, not automatic ownership release.
    with pytest.raises(DomainOwnershipError): enter_domain(factory,'opendata',False)
    assert not query(engine,'SELECT 1 FROM extractions')
