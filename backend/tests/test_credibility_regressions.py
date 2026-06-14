"""Regression tests added during the April-2026 credibility audit.

These tests lock in the fixes applied to remove hardcoded fiscal-year
labels, add reconciliation metadata between the independent debt
sources, and expose accurate scope_detail on the national-budget
endpoint.

Each test is designed to fail if someone re-introduces a hardcoded
"FY 2024/25" / "FY 2023/24" literal, drops the reconciliation block,
or strips the scope_detail label.
"""

from datetime import datetime

import pytest

from models import (
    Audit,
    BudgetLine,
    DebtTimeline,
    Entity,
    EntityType,
    FiscalPeriod,
    Loan,
    Severity,
)


@pytest.fixture()
def seed_credibility_data(db_session, seed_country, seed_source_doc):
    """Seed just enough data to exercise the credibility endpoints."""
    national = Entity(
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="National Government",
        slug="national-government",
    )
    ministry = Entity(
        country_id=seed_country.id,
        type=EntityType.MINISTRY,
        canonical_name="Ministry of Health",
        slug="ministry-of-health",
    )
    county = Entity(
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Test County",
        slug="test-county",
    )
    db_session.add_all([national, ministry, county])
    db_session.flush()

    fp_older = FiscalPeriod(
        country_id=seed_country.id,
        label="FY2023/24",
        start_date=datetime(2023, 7, 1),
        end_date=datetime(2024, 6, 30),
    )
    fp_latest = FiscalPeriod(
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    db_session.add_all([fp_older, fp_latest])
    db_session.flush()

    # Audit rows — two fiscal years, one ministry, one county.
    db_session.add_all(
        [
            Audit(
                entity_id=ministry.id,
                period_id=fp_latest.id,
                finding_text="Procurement irregularity KES 150,000,000",
                severity=Severity.CRITICAL,
                source_document_id=seed_source_doc.id,
            ),
            Audit(
                entity_id=ministry.id,
                period_id=fp_older.id,
                finding_text="Misstatement of expenditure",
                severity=Severity.WARNING,
                source_document_id=seed_source_doc.id,
            ),
            Audit(
                entity_id=county.id,
                period_id=fp_latest.id,
                finding_text="Unsupported vouchers KES 20,000,000",
                severity=Severity.CRITICAL,
                source_document_id=seed_source_doc.id,
            ),
        ]
    )

    # Budget lines for /budget/national
    db_session.add(
        BudgetLine(
            entity_id=national.id,
            period_id=fp_latest.id,
            source_document_id=seed_source_doc.id,
            category="Health",
            allocated_amount=500_000_000_000,
            actual_spent=400_000_000_000,
            currency="KES",
        )
    )
    # County BudgetLine so /budget/overview — which is county-scoped —
    # can resolve a latest fiscal period. Sector is "Health" only, so
    # the Personnel Emoluments trust-guard check is expected to fire.
    db_session.add(
        BudgetLine(
            entity_id=county.id,
            period_id=fp_latest.id,
            source_document_id=seed_source_doc.id,
            category="Health",
            allocated_amount=40_000_000_000,
            actual_spent=32_000_000_000,
            currency="KES",
        )
    )

    # DebtTimeline and Loan rows for reconciliation
    db_session.add(
        DebtTimeline(
            year=2025,
            external=5200,
            domestic=6800,
            total=12000,  # billions KES
            gdp=17500,
            gdp_ratio=68.6,
            source_document_id=seed_source_doc.id,
        )
    )
    db_session.add(
        Loan(
            entity_id=national.id,
            lender="World Bank",
            principal=11_500_000_000_000,
            outstanding=11_500_000_000_000,  # KES, close to timeline 12T
            currency="KES",
            issue_date=datetime(2020, 1, 1),
            source_document_id=seed_source_doc.id,
        )
    )

    db_session.commit()


# ── No-hardcoded-FY regressions ─────────────────────────────────────


class TestNoHardcodedFiscalYears:
    """The audit endpoints must derive fiscal years from the DB, not
    literals. Ensure the payload returns the seeded "FY2024/25" label
    (which the test controls), proving the endpoint reads the DB."""

    def test_audits_federal_reports_oag_report_fiscal_year(
        self, client, seed_credibility_data
    ):
        """audit §3.8: /audits/federal must report the OAG REPORT's own fiscal
        year (from the source document's metadata), NOT the global FISCAL_LABEL
        / DB period the findings happen to be attached to."""
        import json
        from pathlib import Path

        oag_path = (
            Path(__file__).resolve().parent.parent.parent
            / "apis"
            / "oag_national_audit_data.json"
        )
        report_fy = json.loads(oag_path.read_text())["metadata"]["fiscal_year"]

        body = client.get("/api/v1/audits/federal").json()
        # Not a hardcoded code literal (old spacing), and reflects the OAG
        # report's own FY rather than the seeded DB period.
        assert body.get("fiscal_year") != "FY 2023/24"
        assert body.get("fiscal_year") == report_fy
        assert report_fy in body.get("fiscal_years_covered", [])
        assert body.get("_meta", {}).get("fiscal_period") == report_fy

    def test_audits_federal_severity_not_inflated_by_high_mapping(
        self, client, seed_credibility_data
    ):
        """audit §3.3: by_severity must reflect the OAG report's own
        critical/significant/minor counts (key_statistics), not the seed's
        'high'->CRITICAL inflation, so the severity donut isn't overstated."""
        import json
        from pathlib import Path

        oag = json.loads(
            (
                Path(__file__).resolve().parent.parent.parent
                / "apis"
                / "oag_national_audit_data.json"
            ).read_text()
        )
        ks = oag["audit_opinion_summary"]["key_statistics"]
        by_sev = client.get("/api/v1/audits/federal").json().get("by_severity", {})
        assert by_sev.get("CRITICAL") == ks["critical_findings"]
        assert by_sev.get("WARNING") == ks["significant_findings"]
        assert by_sev.get("INFO") == ks["minor_findings"]

    def test_audits_statistics_reports_db_derived_fiscal_year(
        self, client, seed_credibility_data
    ):
        r = client.get("/api/v1/audits/statistics")
        assert r.status_code == 200
        body = r.json()
        assert body.get("fiscal_year") != "FY 2024/25" or body.get(
            "fiscal_year"
        ) == "FY2024/25", (
            "audits/statistics fiscal_year should be DB-derived, not a "
            "hardcoded literal string."
        )
        # The seeded county audit is in FY2024/25.
        assert body.get("fiscal_year") == "FY2024/25"
        assert body.get("_meta", {}).get("fiscal_period") == "FY2024/25"


# ── Reconciliation metadata ─────────────────────────────────────────


class TestDebtReconciliation:
    """Both /debt/national and /debt/timeline must expose a
    ``reconciliation`` block so divergence is surfaced rather than
    hidden."""

    def test_debt_national_reconciliation_present(
        self, client, seed_credibility_data
    ):
        r = client.get("/api/v1/debt/national")
        assert r.status_code == 200
        recon = r.json().get("data", {}).get("reconciliation")
        assert recon is not None, "/debt/national missing reconciliation block"
        assert recon["primary_source"] == "loans_table"
        assert recon["secondary_source"] == "debt_timeline_table"
        assert recon["status"] in {"consistent", "divergent", "unchecked"}

    def test_debt_timeline_reconciliation_present(
        self, client, seed_credibility_data
    ):
        r = client.get("/api/v1/debt/timeline")
        assert r.status_code == 200
        recon = r.json().get("reconciliation")
        assert recon is not None, "/debt/timeline missing reconciliation block"
        assert recon["primary_source"] == "debt_timeline_table"
        assert recon["secondary_source"] == "loans_table"


# ── Scope-detail honesty ────────────────────────────────────────────


class TestBudgetScopeDetail:
    """/budget/national returns only the NG execution subset; its _meta
    must include a scope_detail string so the UI can surface the caveat."""

    def test_budget_national_scope_detail_present(
        self, client, seed_credibility_data
    ):
        r = client.get("/api/v1/budget/national")
        assert r.status_code == 200
        meta = r.json().get("_meta", {})
        detail = meta.get("scope_detail", "")
        assert detail, "/budget/national missing _meta.scope_detail"
        assert "county equitable share" in detail.lower() or "CoB" in detail


# ── Freshness metadata envelope ─────────────────────────────────────


class TestFreshnessMeta:
    """Every top endpoint must stamp the new freshness fields so the
    frontend ResponseMetaBadge can render 'Updated X ago · FY2024/25 ·
    Official source' without guessing."""

    def test_budget_overview_freshness_fields(self, client, seed_credibility_data):
        r = client.get("/api/v1/budget/overview")
        assert r.status_code == 200
        meta = r.json().get("_meta", {})
        # generated_at always present — stamped by _response_meta.
        assert "generated_at" in meta, "/budget/overview missing _meta.generated_at"
        # covers_through echoes the fiscal period actually queried.
        assert meta.get("covers_through"), "/budget/overview missing covers_through"
        # cache_ttl_seconds surfaces the @cached TTL to the client.
        assert meta.get("cache_ttl_seconds") == 1800
        # data_quality must be one of the allowed tokens.
        assert meta.get("data_quality") in {
            "official",
            "estimated",
            "projected",
            "historical",
            "mixed",
            "unknown",
        }

    def test_audits_federal_freshness_fields(self, client, seed_credibility_data):
        import json
        from pathlib import Path

        report_fy = json.loads(
            (
                Path(__file__).resolve().parent.parent.parent
                / "apis"
                / "oag_national_audit_data.json"
            ).read_text()
        )["metadata"]["fiscal_year"]
        r = client.get("/api/v1/audits/federal")
        assert r.status_code == 200
        meta = r.json().get("_meta", {})
        assert "generated_at" in meta
        # covers_through now reflects the OAG report's own FY (audit §3.8),
        # not the global FISCAL_LABEL / seeded period.
        assert meta.get("covers_through") == report_fy
        assert meta.get("cache_ttl_seconds") == 3600

    def test_debt_timeline_freshness_fields(self, client, seed_credibility_data):
        r = client.get("/api/v1/debt/timeline")
        assert r.status_code == 200
        meta = r.json().get("_meta", {})
        assert "generated_at" in meta
        assert meta.get("cache_ttl_seconds") == 86400
        # covers_through is the latest year in the DebtTimeline table.
        assert meta.get("covers_through") == "2025"


# ── Trust-guard surface ──────────────────────────────────────────────


class TestTrustGuards:
    """The trust_guards helpers should flag modeled budget data, empty
    periods, and divergent debt sources. Verify their output is
    surfaced to callers rather than silently logged."""

    def test_budget_sectors_flags_missing_personnel_emoluments(
        self, client, seed_credibility_data
    ):
        r = client.get("/api/v1/budget/overview")
        assert r.status_code == 200
        meta = r.json().get("_meta", {})
        notes = meta.get("quality_notes") or []
        # The seeded budget fixture uses "Health" as its only category.
        # The Personnel Emoluments check should fire.
        joined = " ".join(notes).lower()
        assert "personnel emoluments" in joined, (
            "Trust guard should flag missing Personnel Emoluments "
            "category but quality_notes did not mention it. "
            f"Got: {notes}"
        )

    def test_trust_guards_module_importable(self):
        """Defensive: trust_guards must import cleanly and expose the
        five helpers the endpoints depend on."""
        from services import trust_guards

        for name in (
            "check_budget_sectors",
            "reconcile_debt_totals",
            "check_coverage_staleness",
            "check_period_nonempty",
            "check_plausible_total",
        ):
            assert hasattr(trust_guards, name), f"trust_guards missing {name}"

    def test_coverage_staleness_detects_old_fy(self):
        """Isolated helper test — doesn't need the DB."""
        from services.trust_guards import check_coverage_staleness

        notes = check_coverage_staleness(
            "FY2022/23",
            current_fy_label="FY2025/26",
            max_stale_fys=1,
        )
        assert notes, "check_coverage_staleness should flag FY2022/23 vs FY2025/26"
        assert "behind" in notes[0].lower()

        # Within-threshold case: should NOT flag.
        notes_ok = check_coverage_staleness(
            "FY2024/25",
            current_fy_label="FY2025/26",
            max_stale_fys=1,
        )
        assert notes_ok == []

    def test_debt_reconciliation_divergence_surfaced(self):
        """Isolated helper test for the debt reconciliation math."""
        from services.trust_guards import reconcile_debt_totals

        status, diff, notes = reconcile_debt_totals(
            primary_total_kes=12_000_000_000_000,
            secondary_total_kes=11_000_000_000_000,
            primary_label="loans_table",
            secondary_label="debt_timeline_table",
            threshold_pct=5.0,
        )
        # 12T vs 11T = ~8.3% divergence, above 5% threshold.
        assert status == "divergent"
        assert diff > 5
        assert notes and "diverge" in notes[0].lower()


# ── Post-activation guards (live COB ingestion monitoring) ──────────


class TestPostActivationGuards:
    """Verify the April-2026 post-activation trust checks — freshness,
    category coverage, and repeated failures — fire conservatively
    and downgrade the /budget/overview badge when any one of them
    flags an issue."""

    def test_source_freshness_flags_stale_feed(self):
        from datetime import datetime, timedelta, timezone

        from services.trust_guards import check_source_freshness

        # 200 days ago — well beyond the 120-day COB window.
        stale = datetime.now(timezone.utc) - timedelta(days=200)
        notes = check_source_freshness(
            stale,
            label="County budget feed (COB)",
            max_age_days=120,
        )
        assert notes and "days ago" in notes[0].lower()

    def test_source_freshness_none_flags_missing_feed(self):
        from services.trust_guards import check_source_freshness

        notes = check_source_freshness(
            None,
            label="County budget feed (COB)",
        )
        assert notes
        assert "no successful fetch" in notes[0].lower()

    def test_source_freshness_fresh_feed_stays_silent(self):
        from datetime import datetime, timedelta, timezone

        from services.trust_guards import check_source_freshness

        fresh = datetime.now(timezone.utc) - timedelta(days=10)
        assert check_source_freshness(fresh, label="feed") == []

    def test_category_coverage_flags_total_only(self):
        from services.trust_guards import check_category_coverage

        notes = check_category_coverage(["Total"])
        assert notes and "only aggregate" in notes[0].lower()

    def test_category_coverage_flags_missing_pe(self):
        from services.trust_guards import check_category_coverage

        # Has Recurrent + Development but no Personnel Emoluments.
        notes = check_category_coverage(
            ["Recurrent", "Development", "Health"],
            require_pe=True,
            require_recurrent_dev_split=True,
        )
        assert any("personnel" in n.lower() for n in notes)

    def test_category_coverage_healthy_extraction(self):
        from services.trust_guards import check_category_coverage

        notes = check_category_coverage(
            ["Total", "Recurrent", "Development", "Personnel Emoluments"]
        )
        assert notes == []

    def test_consecutive_failures_flag_three_in_a_row(self):
        from services.trust_guards import check_consecutive_fetch_failures

        notes = check_consecutive_fetch_failures(
            ["completed", "failed", "failed", "failed"],
            domain="counties_budget",
            threshold=3,
        )
        assert notes and "failed" in notes[0].lower()

    def test_consecutive_failures_tolerate_intermittent(self):
        from services.trust_guards import check_consecutive_fetch_failures

        # Two fails then a success ⇒ no alert.
        notes = check_consecutive_fetch_failures(
            ["failed", "failed", "completed"],
            domain="counties_budget",
            threshold=3,
        )
        assert notes == []

    def test_consecutive_failures_completed_with_errors_is_success(self):
        from services.trust_guards import check_consecutive_fetch_failures

        # Kenya seeds frequently return completed_with_errors for
        # non-critical issues — that must NOT count as a failure.
        notes = check_consecutive_fetch_failures(
            ["completed_with_errors"] * 5,
            domain="counties_budget",
            threshold=3,
        )
        assert notes == []
