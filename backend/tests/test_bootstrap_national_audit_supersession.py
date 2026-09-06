"""The national audit fixture could never stop being stale.

``oag_national_audit_data.json`` declares ``live_source: "audits"`` but no
``superseded_check``, so ``_supersession()`` returned ``(False, None)`` for it
unconditionally. At 630 days against a 180-day limit it pinned
``bootstrap_provenance`` to ``fixture_stale`` on every run, which the nightly's
freshness gate reports as CRITICAL — the failure in runs 33939021023 and
34006483292. No amount of live seeding could clear it: nothing was asking.

The other two fixtures got checks (18466fc, 2760328). This one was missed, and
because it is the OLDEST of the three it is the file the stale message names.

What "superseded" means here is the module's own definition — nothing in the
file can reach a reader:

  * every ``Audit`` row it mints hangs off a source document with no URL, so
    ``publishable_audit_criterion`` withholds it; and
  * its ``audit_opinion_summary`` (served straight off disk by
    ``/audits/federal``) is withheld by ``file_source_provenance_failure``,
    because the file cites a homepage rather than a document.

Whether national audit findings are ARRIVING is a different question, asked by
a different gate — ``TableRule("Audit findings", dataset_id=
"oag_national_audits")``. This check must never be read as answering it.
"""

import json
from datetime import date, datetime, timezone

import pytest

import bootstrap
from models import (
    Audit,
    Country,
    DocumentType,
    Entity,
    EntityType,
    FiscalPeriod,
    Severity,
    SourceDocument,
)

NAME = bootstrap.NATIONAL_AUDIT_PATH.name


@pytest.fixture()
def national(db_session):
    """The state bootstrap leaves behind: rows on a URL-less fixture document."""
    country = Country(
        name="Kenya",
        iso_code="KEN",
        currency="KES",
        timezone="Africa/Nairobi",
        default_locale="en-KE",
    )
    db_session.add(country)
    db_session.flush()

    period = FiscalPeriod(
        country_id=country.id,
        label="FY2023/24",
        start_date=date(2023, 7, 1),
        end_date=date(2024, 6, 30),
    )
    entity = Entity(
        country_id=country.id,
        type=EntityType.NATIONAL,
        canonical_name="Republic of Kenya",
        slug="republic-of-kenya",
    )
    # Exactly what _ensure_source_document builds for this file: the metadata
    # block carries no "url" key, so the column is NULL.
    doc = SourceDocument(
        title="Report of the Auditor General on the National Government",
        url=None,
        publisher="Office of the Auditor General",
        doc_type=DocumentType.AUDIT,
        country_id=country.id,
        fetch_date=datetime(2024, 12, 15, tzinfo=timezone.utc),
        meta={"source": NAME, "scope": "national"},
    )
    db_session.add_all([period, entity, doc])
    db_session.flush()

    for i in range(3):
        db_session.add(
            Audit(
                entity_id=entity.id,
                period_id=period.id,
                finding_text=f"national finding {i}",
                severity=Severity.WARNING,
                source_document_id=doc.id,
            )
        )
    db_session.flush()
    return db_session, doc, entity, period


def _national_file(provenance):
    return next(f for f in provenance["files"] if f["file"] == NAME)


class TestTheGapItself:
    def test_the_fixture_declares_a_supersession_check(self):
        """The bug, stated directly: this entry had no check at all."""
        spec = bootstrap._FIXTURE_DECLARATIONS[NAME]
        assert spec.get("superseded_check"), (
            f"{NAME} declares live_source={spec['live_source']!r} but nothing "
            "ever asks whether that source took over, so it is stale forever"
        )

    def test_the_named_check_is_registered(self):
        spec = bootstrap._FIXTURE_DECLARATIONS[NAME]
        assert spec["superseded_check"] in bootstrap._SUPERSESSION_CHECKS


class TestItFires:
    def test_it_is_superseded_when_nothing_in_it_reaches_a_reader(self, national):
        session, *_ = national
        assert _national_file(bootstrap.bootstrap_provenance(session))["superseded"]

    def test_it_stops_being_the_file_the_stale_message_blames(self, national):
        session, *_ = national
        p = bootstrap.bootstrap_provenance(session)
        assert NAME not in p["stale_files"]
        assert NAME in p["superseded_files"]

    def test_the_evidence_names_both_surfaces(self, national):
        """A bare True is not auditable — say what was checked."""
        session, *_ = national
        evidence = _national_file(bootstrap.bootstrap_provenance(session))[
            "supersession_evidence"
        ]
        assert "publication gate" in evidence
        assert "opinion" in evidence.lower()


class TestItRefuses:
    """The ways it must NOT fire — the part that keeps it honest."""

    def test_without_a_session_it_is_not_superseded(self):
        assert not _national_file(bootstrap.bootstrap_provenance(None))["superseded"]

    def test_a_publishable_row_from_the_file_blocks_it(self, national):
        """Give the fixture document a URL and its rows reach readers again."""
        session, doc, *_ = national
        doc.url = "https://oagkenya.go.ke/reports/national-fy2023-24.pdf"
        session.add(doc)
        session.flush()

        f = _national_file(bootstrap.bootstrap_provenance(session))
        assert f["superseded"] is False
        assert "3" in f["supersession_evidence"]

    def test_a_citable_file_blocks_it(self, national, tmp_path, monkeypatch):
        """If the file gained a real document citation, /audits/federal would
        publish its opinion summary — so it is no longer vestigial."""
        session, *_ = national
        payload = json.loads(bootstrap.NATIONAL_AUDIT_PATH.read_text())
        payload["metadata"]["url"] = "https://oagkenya.go.ke/reports/ng-fy2023-24.pdf"
        payload["metadata"]["page"] = "p. 14"
        path = tmp_path / NAME
        path.write_text(json.dumps(payload))
        monkeypatch.setattr(bootstrap, "NATIONAL_AUDIT_PATH", path)

        superseded, evidence = bootstrap._SUPERSESSION_CHECKS[
            bootstrap._FIXTURE_DECLARATIONS[NAME]["superseded_check"]
        ](session)
        assert superseded is False
        assert "opinion" in evidence.lower()

    def test_an_unreadable_file_is_not_superseded(self, national, tmp_path, monkeypatch):
        session, *_ = national
        missing = tmp_path / "gone.json"
        monkeypatch.setattr(bootstrap, "NATIONAL_AUDIT_PATH", missing)
        superseded, evidence = bootstrap._SUPERSESSION_CHECKS[
            bootstrap._FIXTURE_DECLARATIONS[NAME]["superseded_check"]
        ](session)
        assert superseded is False
        assert "could not read" in evidence
