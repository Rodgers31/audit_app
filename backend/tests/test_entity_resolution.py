"""Tolerant entity resolution — a mangled county name must not lose data.

The COB county BIRR PDF yielded a cell reading "Taita Tav eta" (pdfplumber
split the word on glyph spacing). That slugified to `taita-tav-eta-county`,
matched no entity, and the county's entire budget row was DROPPED with only
a warning. Any of the 47 counties can be mangled on any future report, so
resolution tolerates spacing artifacts instead of aliasing one name.
"""

from __future__ import annotations

import pytest
from models import Entity, EntityType
from seeding.utils import resolve_entity_by_slug


@pytest.fixture()
def counties(db_session, seed_country):
    rows = [
        Entity(id=7001, country_id=seed_country.id, type=EntityType.COUNTY,
               canonical_name="Taita Taveta County", slug="taita-taveta-county"),
        Entity(id=7002, country_id=seed_country.id, type=EntityType.COUNTY,
               canonical_name="Murang'a County", slug="muranga-county"),
        Entity(id=7003, country_id=seed_country.id, type=EntityType.COUNTY,
               canonical_name="Nairobi County", slug="nairobi-county"),
        Entity(id=7004, country_id=seed_country.id, type=EntityType.MINISTRY,
               canonical_name="Ministry of Health", slug="ministry-of-health"),
    ]
    db_session.add_all(rows)
    db_session.commit()
    return rows


class TestResolveEntityBySlug:
    def test_exact_match(self, db_session, counties):
        e, how = resolve_entity_by_slug(db_session, "nairobi-county")
        assert e.slug == "nairobi-county" and how == "exact"

    def test_the_actual_defect_taita_taveta(self, db_session, counties):
        """THE bug, from a real 2026-08-29 run against the live COB PDF."""
        e, how = resolve_entity_by_slug(
            db_session, "taita-tav-eta-county", entity_type=EntityType.COUNTY
        )
        assert e is not None, "county was silently dropped"
        assert e.slug == "taita-taveta-county"
        assert how == "despaced"

    @pytest.mark.parametrize("mangled", [
        "taitataveta-county", "taita-taveta", "ta-ita-tav-eta-county",
        "TAITA-TAVETA-COUNTY",
    ])
    def test_other_spacing_artifacts_of_the_same_class(
        self, db_session, counties, mangled
    ):
        e, _ = resolve_entity_by_slug(
            db_session, mangled, entity_type=EntityType.COUNTY
        )
        assert e is not None and e.slug == "taita-taveta-county"

    def test_apostrophe_name_still_resolves(self, db_session, counties):
        e, _ = resolve_entity_by_slug(db_session, "murang'a-county")
        assert e is not None and e.slug == "muranga-county"

    def test_genuinely_unknown_still_returns_none(self, db_session, counties):
        """Tolerance must not become "match anything" — a real miss must
        still be reported, or the fix would hide the next defect."""
        e, how = resolve_entity_by_slug(
            db_session, "atlantis-county", entity_type=EntityType.COUNTY
        )
        assert e is None and how is None

    def test_type_filter_prevents_cross_type_match(self, db_session, counties):
        e, _ = resolve_entity_by_slug(
            db_session, "ministry-of-health", entity_type=EntityType.COUNTY
        )
        assert e is None, "a ministry must never satisfy a county lookup"

    def test_empty_slug_is_not_a_match(self, db_session, counties):
        assert resolve_entity_by_slug(db_session, "") == (None, None)
