"""The invented stalled-projects records are no longer written or served (#230).

Until this change ``seeding/real_data/stalled_projects.json`` held 25 records
nobody read from any document, the domain wrote them into ``Entity.meta``
nightly, and ``/counties/{id}/comprehensive`` returned them verbatim. On
2026-09-26 production answered for Nairobi::

    {"count": 2, "total_contracted_value": 4090000000, ...,
     "projects": [{"project_name": "Eastlands Urban Renewal Phase II",
                   "oag_reference": "OAG/NRB/2023/INF-012", ...}, ...]}

The two Nairobi records below are copied verbatim from that response, so the
test exercises exactly what production holds until the next nightly runs.
"""

from __future__ import annotations

import pytest
from models import Entity, EntityType

# Verbatim from GET /api/v1/counties/1/comprehensive, 2026-09-26 22:24 UTC.
PRODUCTION_NAIROBI_ROWS = [
    {
        "reason": "Contractor abandoned site after payment disputes; pending arbitration",
        "sector": "Infrastructure",
        "status": "stalled",
        "start_year": 2019,
        "amount_paid": 1920000000,
        "project_name": "Eastlands Urban Renewal Phase II",
        "oag_reference": "OAG/NRB/2023/INF-012",
        "completion_pct": 35,
        "contracted_amount": 3200000000,
        "expected_completion": 2022,
    },
    {
        "reason": "Scope changes and land acquisition delays",
        "sector": "Water & Sanitation",
        "status": "delayed",
        "start_year": 2020,
        "amount_paid": 534000000,
        "project_name": "Dandora Estate Sewer Rehabilitation",
        "oag_reference": "OAG/NRB/2023/WS-007",
        "completion_pct": 42,
        "contracted_amount": 890000000,
        "expected_completion": 2023,
    },
]

PRODUCTION_META = {
    "stalled_projects": PRODUCTION_NAIROBI_ROWS,
    "stalled_projects_count": 2,
    "stalled_projects_total_value": 4090000000,
    "stalled_projects_total_paid": 2454000000,
    # Not ours: must survive the clean-up.
    "governor": "Johnson Sakaja",
}


@pytest.fixture()
def nairobi(db_session, seed_country):
    entity = Entity(
        id=1,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nairobi County",
        slug="nairobi-county",
        meta=dict(PRODUCTION_META),
    )
    db_session.add(entity)
    db_session.commit()
    return entity


def test_the_fixture_is_gone():
    import pathlib

    import seeding

    root = pathlib.Path(seeding.__file__).resolve().parent
    assert not (root / "real_data" / "stalled_projects.json").exists()


class TestTheApiServesOnlyEvidence:
    def test_production_rows_are_withheld_not_published(self, client, nairobi):
        body = client.get("/api/v1/counties/1/comprehensive").json()
        block = body["stalled_projects"]
        assert block["projects"] == []
        # None, not 0: nobody has said Nairobi has zero stalled projects.
        assert block["count"] is None
        assert block["total_contracted_value"] is None
        assert block["total_amount_paid"] is None
        assert block["reason"] == "no_evidence_backed_source"
        assert block["withheld"] == {
            "count": 2,
            "by_reason": {"no_source_document": 2},
        }

    def test_an_evidenced_row_is_still_published(self, client, nairobi, db_session):
        """Control: a gate that withheld everything would pass the test above."""
        row = {
            "project_name": "Construction of Kasarani ward office",
            "estimated_value_kes": 12_500_000.0,
            "amount_paid_kes": None,  # "-" in the table: missing, never 0
            "source_url": "https://cob.go.ke/download/example/?wpdmdl=1",
            "source_page": 611,
            "as_of": "2026-06-30",
            "reported_by": "County treasury, as reported to the Controller of Budget",
        }
        nairobi.meta = {"stalled_projects": {"rows": [row, PRODUCTION_NAIROBI_ROWS[0]]}}
        db_session.commit()

        block = client.get("/api/v1/counties/1/comprehensive?nocache=1").json()[
            "stalled_projects"
        ]
        assert block["count"] == 1
        assert block["projects"][0]["project_name"] == row["project_name"]
        assert block["total_contracted_value"] == 12_500_000.0
        # The one row with a paid figure is missing it, so there is no total.
        assert block["total_amount_paid"] is None
        assert block["withheld"]["count"] == 1


class TestTheDomainCleansProduction:
    def _run(self, db_session, dry_run=False):
        from seeding import freshness
        from seeding.config import SeedingSettings
        from seeding.domains import stalled_projects
        from seeding.types import DomainRunContext

        freshness.reset("stalled_projects")
        result = stalled_projects.run(
            db_session, SeedingSettings(), DomainRunContext(since=None, dry_run=dry_run)
        )
        return result, freshness.get("stalled_projects")

    def test_the_nightly_removes_every_key_it_owns(self, db_session, nairobi):
        result, _ = self._run(db_session)
        db_session.refresh(nairobi)
        assert {k for k in nairobi.meta if k.startswith("stalled_projects")} == set()
        assert nairobi.meta["governor"] == "Johnson Sakaja"
        assert result.metadata["cleared_keys"] == 4

    def test_a_dry_run_touches_nothing(self, db_session, nairobi):
        self._run(db_session, dry_run=True)
        db_session.refresh(nairobi)
        assert nairobi.meta == PRODUCTION_META

    def test_it_writes_no_new_records_and_says_so(self, db_session, nairobi):
        result, mode = self._run(db_session)
        assert result.items_created == 0
        assert mode["mode"] != "fixture"
