"""The county_officials domain writes deputy governors from the Council (#231).

What a reader sees depends on three things this pins:

* a listed deputy is stored with its provenance;
* a county the Council no longer lists has its stored deputy REMOVED, so a
  vacancy is not covered over by last year's name;
* a failed deputies page leaves the governors intact and is reported as a
  domain error, not swallowed.
"""

from contextlib import contextmanager

import pytest

from seeding.extractors.cog_governors import (
    DEPUTIES_SOURCE_URL,
    KENYAN_COUNTIES,
    SOURCE_URL,
)
from seeding.types import DomainRunContext
from tests.test_cog_governors import _synthetic, page


def _deputy(county):
    return _synthetic(county).replace("Mwangi", "Wanjiru")


class _Resp:
    def __init__(self, text):
        self.text = text


def _client_serving(pages):
    class _Client:
        def get(self, url, headers=None, raise_for_status=False):
            body = pages[url]
            if isinstance(body, Exception):
                raise body
            return _Resp(body)

    @contextmanager
    def factory(_settings):
        yield _Client()

    return factory


@pytest.fixture
def counties(db_session, seed_country):
    from models import Entity, EntityType

    rows = []
    for i, name in enumerate(KENYAN_COUNTIES, start=1):
        e = Entity(
            id=1000 + i,
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name=f"{name} County",
            slug=name.lower().replace(" ", "-"),
            meta={},
        )
        db_session.add(e)
        rows.append(e)
    db_session.commit()
    return {e.canonical_name.removesuffix(" County"): e for e in rows}


def _run(db_session, monkeypatch, pages):
    import seeding.domains.county_officials as domain
    from seeding.config import SeedingSettings

    monkeypatch.setattr(domain, "create_http_client", _client_serving(pages))
    result = domain.run(
        db_session, SeedingSettings(), DomainRunContext(since=None, dry_run=False)
    )
    db_session.commit()
    return result


GOVERNORS = page([(_synthetic(c), c) for c in KENYAN_COUNTIES])


def test_deputies_are_stored_with_provenance(db_session, monkeypatch, counties):
    deputies = page([(_deputy(c), c) for c in KENYAN_COUNTIES if c != "Homa Bay"])
    result = _run(db_session, monkeypatch, {SOURCE_URL: GOVERNORS, DEPUTIES_SOURCE_URL: deputies})

    meru = counties["Meru"]
    db_session.refresh(meru)
    assert meru.meta["deputy_governor"] == "Meru Wanjiru"
    assert meru.meta["deputy_governor_provenance"]["source_url"] == DEPUTIES_SOURCE_URL
    assert meru.meta["deputy_governor_provenance"]["source"] == "Council of Governors"
    assert result.metadata["deputies"] == 46
    assert result.errors == []


def test_an_unlisted_deputy_is_removed_not_kept(db_session, monkeypatch, counties):
    homa = counties["Homa Bay"]
    homa.meta = {"deputy_governor": "Last Year's Name", "deputy_governor_provenance": {"x": 1}}
    db_session.commit()

    deputies = page([(_deputy(c), c) for c in KENYAN_COUNTIES if c != "Homa Bay"])
    _run(db_session, monkeypatch, {SOURCE_URL: GOVERNORS, DEPUTIES_SOURCE_URL: deputies})

    db_session.refresh(homa)
    assert "deputy_governor" not in homa.meta
    assert "deputy_governor_provenance" not in homa.meta


def test_deputy_who_is_also_the_governor_is_not_stored(db_session, monkeypatch, counties):
    """Meru's case: the deputy was elevated. If the deputies page lags the
    governors page, the same person would be shown in both roles."""
    deputies = page(
        [(_deputy(c), c) for c in KENYAN_COUNTIES if c != "Meru"]
        + [(_synthetic("Meru"), "Meru")]
    )
    result = _run(db_session, monkeypatch, {SOURCE_URL: GOVERNORS, DEPUTIES_SOURCE_URL: deputies})

    meru = counties["Meru"]
    db_session.refresh(meru)
    assert meru.meta["governor"] == "Meru Mwangi"
    assert "deputy_governor" not in meru.meta
    assert any("Meru" in c for c in result.metadata["deputy_checks"])


def test_deputies_page_failure_keeps_governors_and_is_reported(
    db_session, monkeypatch, counties
):
    result = _run(
        db_session,
        monkeypatch,
        {SOURCE_URL: GOVERNORS, DEPUTIES_SOURCE_URL: ConnectionError("down")},
    )
    meru = counties["Meru"]
    db_session.refresh(meru)
    assert meru.meta["governor"] == "Meru Mwangi"
    assert result.items_processed == 47
    assert any("deputy" in e.lower() for e in result.errors)
    assert result.metadata["deputies_quarantine_reason"] == "source_unreachable"
