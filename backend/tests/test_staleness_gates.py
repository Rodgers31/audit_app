"""Freshness gates must FIRE — a check that cannot fail is not a check.

These gates replace row-count floors that passed every night for months
("[OK] Audit Records: 27 rows (expected >= 20)") while the underlying
tables had not gained a row in 6-11 weeks. Every test below is a positive
control: it constructs the exact condition the nightly missed and asserts
the gate reports FAIL.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from models import (
    Audit,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    FiscalPeriod,
    IngestionJob,
    IngestionStatus,
    Severity,
    SourceDocument,
)
from seeding.staleness import (
    FAIL,
    OK,
    WARN,
    check_ingestion_freshness,
    check_table_freshness,
)

NOW = datetime(2026, 8, 29, tzinfo=timezone.utc)


def _finding(findings, label):
    return next(f for f in findings if f.label == label)


class TestTableFreshness:
    def test_fires_on_a_frozen_table(self, db_session, seed_country):
        """THE defect: audits frozen far beyond the OAG publication cycle."""
        doc = SourceDocument(
            id=9001, country_id=seed_country.id, publisher="OAG",
            title="t", url="https://x/y.pdf",
            fetch_date=NOW - timedelta(days=500),
            doc_type=DocumentType.AUDIT, status=DocumentStatus.AVAILABLE,
        )
        ent = Entity(id=9001, country_id=seed_country.id,
                     type=EntityType.MINISTRY, canonical_name="M", slug="m-stale")
        per = FiscalPeriod(id=9001, country_id=seed_country.id, label="FY2019/20",
                           start_date=datetime(2019, 7, 1),
                           end_date=datetime(2020, 6, 30))
        db_session.add_all([doc, ent, per])
        db_session.flush()
        db_session.add(Audit(
            entity_id=ent.id, period_id=per.id, finding_text="old",
            severity=Severity.INFO, source_document_id=doc.id,
            created_at=NOW - timedelta(days=500),
        ))
        db_session.commit()

        f = _finding(check_table_freshness(db_session, now=NOW), "Audit findings")
        assert f.level == FAIL
        assert "500 days old" in f.message

    def test_passes_when_data_is_current(self, db_session, seed_country):
        doc = SourceDocument(
            id=9002, country_id=seed_country.id, publisher="OAG", title="t",
            url="https://x/y.pdf", fetch_date=NOW - timedelta(days=2),
            doc_type=DocumentType.AUDIT, status=DocumentStatus.AVAILABLE,
        )
        ent = Entity(id=9002, country_id=seed_country.id,
                     type=EntityType.MINISTRY, canonical_name="M2", slug="m2-fresh")
        per = FiscalPeriod(id=9002, country_id=seed_country.id, label="FY2024/25",
                           start_date=datetime(2024, 7, 1),
                           end_date=datetime(2025, 6, 30))
        db_session.add_all([doc, ent, per])
        db_session.flush()
        db_session.add(Audit(
            entity_id=ent.id, period_id=per.id, finding_text="new",
            severity=Severity.INFO, source_document_id=doc.id,
            created_at=NOW - timedelta(days=2),
        ))
        db_session.commit()

        assert _finding(
            check_table_freshness(db_session, now=NOW), "Audit findings"
        ).level == OK

    def test_empty_table_is_not_silently_ok(self, db_session, seed_country):
        f = _finding(check_table_freshness(db_session, now=NOW), "Audit findings")
        assert f.level == FAIL
        assert "EMPTY" in f.message


class TestIngestionFreshness:
    def _job(self, domain, days_ago, mode, reason=None):
        meta = {"source_mode": mode} if mode else {}
        if reason:
            meta["source_fallback_reason"] = reason
        return IngestionJob(
            domain=domain, status=IngestionStatus.COMPLETED, dry_run=False,
            started_at=(NOW - timedelta(days=days_ago)).replace(tzinfo=None),
            items_processed=20, items_created=0, items_updated=0,
            errors=[], meta=meta,
        )

    def test_fires_when_every_run_used_a_fixture(self, db_session):
        """THE defect: national_budget processed 20 rows a night from a
        git-tracked fixture, wrote nothing, and reported [OK]."""
        for d in (1, 2, 3):
            db_session.add(self._job("national_budget", d, "fixture",
                                     "live_fetch_failed"))
        db_session.commit()

        f = _finding(
            check_ingestion_freshness(db_session, now=NOW), "national_budget ingestion"
        )
        assert f.level == FAIL
        assert "FIXTURE" in f.message and "live_fetch_failed" in f.message

    def test_passes_when_publisher_was_reached(self, db_session):
        db_session.add(self._job("national_budget", 3, "fixture", "x"))
        db_session.add(self._job("national_budget", 1, "live"))
        db_session.commit()
        assert _finding(
            check_ingestion_freshness(db_session, now=NOW), "national_budget ingestion"
        ).level == OK

    def test_unrecorded_provenance_is_not_reported_healthy(self, db_session):
        """Absence of evidence must never render as OK — that is the exact
        false-green this module exists to eliminate."""
        db_session.add(self._job("legacy_domain", 1, None))
        db_session.commit()
        f = _finding(
            check_ingestion_freshness(db_session, now=NOW), "legacy_domain ingestion"
        )
        assert f.level == WARN
        assert "not confirmed healthy" in f.message

    def test_missing_domain_is_flagged(self, db_session):
        f = _finding(
            check_ingestion_freshness(db_session, now=NOW, domains=["ghost"]),
            "ghost ingestion",
        )
        assert f.level == WARN
        assert "no run recorded" in f.message


# ── Every domain must declare where its data came from ────────────────
class TestEveryDomainRecordsProvenance:
    """`no-silent-fallbacks`, applied to the whole registry.

    Seven domains recorded nothing until 2026-08-29, so
    ``check_ingestion_freshness`` reported "provenance unknown — not
    confirmed healthy" for half the pipeline every night. WARN forever is
    the same failure shape as OK forever: nobody can act on it, and a domain
    that genuinely went dark looks identical to one that was never wired up.

    This test walks the ACTUAL registry rather than a hand-written list, so
    a new domain added without provenance fails here instead of quietly
    joining the unknown pile.
    """

    def _registered(self):
        from seeding.registries import REGISTRY, load_builtin_domains

        load_builtin_domains()
        return sorted(REGISTRY.domains())

    def test_registry_is_not_empty(self):
        """Positive control for the walk itself: an empty registry would
        make every assertion below vacuous."""
        assert len(self._registered()) >= 14

    def test_every_domain_marks_its_source_mode(self):
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1] / "seeding" / "domains"
        missing = []
        for domain in self._registered():
            package = root / domain
            sources = "".join(
                path.read_text() for path in package.rglob("*.py")
            )
            if "mark_live(" not in sources and "mark_fixture(" not in sources:
                missing.append(domain)
        assert missing == [], (
            f"domains with no provenance instrumentation: {missing}. Every "
            f"fetch branch must call mark_live() or mark_fixture(); see "
            f"seeding/freshness.py."
        )

    def test_a_domain_that_only_marks_live_still_covers_its_fallback(self):
        """A fetcher that marks live on success but says nothing on failure
        reports 'unknown' exactly when it matters most. Any domain with a
        fixture fallback must have BOTH calls."""
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[1] / "seeding" / "domains"
        # imf_weo has no fixture; it marks fixture on failure and live on
        # success, so it is covered by the same rule.
        one_sided = []
        for domain in self._registered():
            sources = "".join(
                path.read_text()
                for path in (root / domain).rglob("*.py")
            )
            has_live = "mark_live(" in sources
            has_fixture = "mark_fixture(" in sources
            if has_live and not has_fixture:
                one_sided.append(domain)
        assert one_sided == [], (
            f"domains that record success but not failure: {one_sided}"
        )

    def test_the_gate_reads_what_the_fetchers_write(self):
        """End-to-end on the contract itself: a recorded live mode must be
        what check_ingestion_freshness reports OK for."""
        from seeding import freshness

        freshness.reset("national_gdp")
        freshness.mark_live("national_gdp", detail="World Bank")
        assert freshness.get("national_gdp")["mode"] == freshness.LIVE
        assert not freshness.is_stale("national_gdp")

        freshness.reset("national_gdp")
        freshness.mark_fixture("national_gdp", reason="worldbank_unreachable")
        assert freshness.is_stale("national_gdp")


# ── A run that REFUSED to publish is neither live nor fixture ─────────
class TestRefusedRuns:
    """The fifth mode: the domain reached a verdict of "do not publish".

    ``national_debt.fetcher`` raises ``DebtRegisterIncomplete`` when the IDS
    creditor pull is quarantined, because serving the fixture's external rows
    would put a 13.34T headline against the register's 12.22T. The domain
    writes nothing and the previous seed's rows stand.

    Before this, such a run reached no ``mark_*`` at all, recorded ``unknown``,
    and fell through to the all-fixture branch, which printed:

        FAIL  national_debt ingestion
              served from a FIXTURE in all 1 recent run(s) — the publisher was
              never successfully read (reasons: unrecorded)

    Right severity, false prose. Nothing was served from a fixture; nothing was
    served at all, and the reason was known. The gate must say what happened.
    """

    def _job(self, domain, days_ago, mode, reason=None, detail=None):
        meta = {"source_mode": mode} if mode else {}
        if reason:
            meta["source_fallback_reason"] = reason
        if detail:
            # The key ``seeding/cli.py`` actually writes from
            # ``freshness.get()["detail"]``.
            meta["source_detail"] = detail
        return IngestionJob(
            domain=domain, status=IngestionStatus.COMPLETED_WITH_ERRORS,
            dry_run=False,
            started_at=(NOW - timedelta(days=days_ago)).replace(tzinfo=None),
            items_processed=0, items_created=0, items_updated=0,
            errors=["Register refused, nothing written"], meta=meta,
        )

    def test_a_refused_run_is_not_described_as_a_fixture(self, db_session):
        """THE defect. A refusal published NOTHING — not a fixture."""
        db_session.add(
            self._job("national_debt", 1, "refused", "external_register_incomplete")
        )
        db_session.commit()

        f = _finding(
            check_ingestion_freshness(db_session, now=NOW), "national_debt ingestion"
        )
        assert f.level == FAIL
        assert "FIXTURE" not in f.message.upper(), (
            f"a refused run was reported as fixture-served: {f.message}"
        )
        assert "refused to publish" in f.message
        assert "external_register_incomplete" in f.message

    def test_the_message_tells_the_operator_what_is_on_the_page(self, db_session):
        """"Nothing was written" is only half the fact an operator needs; the
        other half is that the site is still serving something."""
        db_session.add(
            self._job("national_debt", 1, "refused", "external_register_incomplete")
        )
        db_session.commit()

        f = _finding(
            check_ingestion_freshness(db_session, now=NOW), "national_debt ingestion"
        )
        assert "previous seed" in f.message

    def test_the_message_names_the_gate_that_refused(self, db_session):
        """The reason slug says the register was incomplete; the DETAIL says
        which gate said so, which is the part somebody can act on."""
        db_session.add(
            self._job(
                "national_debt", 1, "refused", "external_register_incomplete",
                detail="IDS creditor pull did not apply (returned_no_creditors)",
            )
        )
        db_session.commit()

        f = _finding(
            check_ingestion_freshness(db_session, now=NOW), "national_debt ingestion"
        )
        assert "returned_no_creditors" in f.message

    def test_an_unreasoned_refusal_still_fails_rather_than_going_quiet(
        self, db_session
    ):
        """A refusal with no recorded reason is still a refusal. It must not
        fall back to the fixture prose, and it must not go OK."""
        db_session.add(self._job("national_debt", 1, "refused"))
        db_session.commit()

        f = _finding(
            check_ingestion_freshness(db_session, now=NOW), "national_debt ingestion"
        )
        assert f.level == FAIL
        assert "refused to publish" in f.message
        assert "FIXTURE" not in f.message.upper()

    def test_a_refusal_outranks_older_live_runs(self, db_session):
        """The false green this branch has to beat.

        The window holds 14 days. On 2026-09-07 production's window held 8
        live national_debt runs, so the first night the refusal fires the
        ``"live" in modes`` branch would have printed

            [OK] national_debt ingestion: reached the publisher in 8/22 ...

        while the register was being refused every night. A refusal is a claim
        about NOW — what is on the page today — so it is judged on the most
        recent run, the same way supersession is (see ``_latest_run_reasons``).
        """
        db_session.add(self._job("national_debt", 3, "live"))
        db_session.add(
            self._job("national_debt", 1, "refused", "external_register_incomplete")
        )
        db_session.commit()

        f = _finding(
            check_ingestion_freshness(db_session, now=NOW), "national_debt ingestion"
        )
        assert f.level == FAIL, (
            f"a window with older live runs hid tonight's refusal: {f.message}"
        )
        assert "refused to publish" in f.message

    def test_the_count_is_honest_when_only_some_runs_refused(self, db_session):
        """Never "all N" when it was not all N — that is the same class of
        false sentence this branch exists to remove."""
        db_session.add(self._job("national_debt", 3, "live"))
        db_session.add(
            self._job("national_debt", 1, "refused", "external_register_incomplete")
        )
        db_session.commit()

        f = _finding(
            check_ingestion_freshness(db_session, now=NOW), "national_debt ingestion"
        )
        assert "all 2" not in f.message, f"claimed all runs refused: {f.message}"
        assert "1 of 2 recent run(s)" in f.message

    # ── NEGATIVE CONTROLS: the branch must be able to NOT fire ────────
    def test_a_live_run_after_a_refusal_is_ok_again(self, db_session):
        """The pull recovers, the register publishes. The gate must clear —
        a branch that cannot turn off becomes a permanently red gate, which
        is how real breakages hide."""
        db_session.add(
            self._job("national_debt", 3, "refused", "external_register_incomplete")
        )
        db_session.add(self._job("national_debt", 1, "live"))
        db_session.commit()

        assert _finding(
            check_ingestion_freshness(db_session, now=NOW), "national_debt ingestion"
        ).level == OK

    def test_an_ordinary_fixture_run_still_reads_as_a_fixture(self, db_session):
        """The neighbouring branch must be untouched: a domain that really did
        serve a git-tracked file must still say so."""
        db_session.add(self._job("national_budget", 1, "fixture", "live_fetch_failed"))
        db_session.commit()

        f = _finding(
            check_ingestion_freshness(db_session, now=NOW), "national_budget ingestion"
        )
        assert f.level == FAIL
        assert "FIXTURE" in f.message
        assert "refused" not in f.message


# ── The shared module owns the mode, not national_debt ────────────────
class TestRefusedIsASharedMode:
    def test_the_mode_is_defined_in_the_shared_module(self):
        from seeding import freshness

        assert freshness.REFUSED == "refused"
        assert freshness.REFUSED not in (
            freshness.LIVE, freshness.FIXTURE, freshness.PARTIAL, freshness.UNKNOWN
        )

    def test_any_domain_can_record_a_refusal(self):
        """No national_debt special-casing: the helper takes a domain name."""
        from seeding import freshness

        freshness.reset("some_other_domain")
        freshness.mark_refused(
            "some_other_domain", reason="gate_said_no", detail="why"
        )
        recorded = freshness.get("some_other_domain")
        assert recorded["mode"] == freshness.REFUSED
        assert recorded["reason"] == "gate_said_no"
        assert recorded["detail"] == "why"
        freshness.reset("some_other_domain")

    def test_a_refusal_is_stale(self):
        from seeding import freshness

        freshness.reset("some_other_domain")
        freshness.mark_refused("some_other_domain", reason="gate_said_no")
        assert freshness.is_stale("some_other_domain") is True
        freshness.reset("some_other_domain")

    def test_the_recorded_shape_is_what_the_cli_copies_onto_the_job_row(self):
        """``cli.py`` reads exactly these keys off ``freshness.get()``. If a
        refusal recorded them under different names the mode would reach the
        gate as ``None`` and land back in the unknown-provenance branch."""
        from seeding import freshness

        freshness.reset("some_other_domain")
        freshness.mark_refused(
            "some_other_domain", reason="gate_said_no", detail="which gate"
        )
        provenance = freshness.get("some_other_domain")
        assert provenance.get("mode") == "refused"
        assert provenance.get("reason") == "gate_said_no"
        assert provenance.get("detail") == "which gate"
        freshness.reset("some_other_domain")

    def test_the_module_docstring_comment_counts_every_mode(self):
        """The comment above the ContextVar undercounted the modes for the
        whole life of ``partial`` — which is how the fifth one nearly got
        missed as well. Any mode constant absent from it fails here."""
        import pathlib

        source = (
            pathlib.Path(__file__).resolve().parents[1] / "seeding" / "freshness.py"
        ).read_text()
        comment = next(
            line for line in source.splitlines() if line.startswith("# mode ∈")
        )
        from seeding import freshness

        missing = [
            m for m in (
                freshness.LIVE, freshness.FIXTURE, freshness.PARTIAL,
                freshness.REFUSED, freshness.UNKNOWN,
            )
            if f'"{m}"' not in comment
        ]
        assert missing == [], f"modes absent from the comment: {missing}"
