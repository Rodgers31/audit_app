"""#388/#391: real persisted evidence and endpoint selection controls."""
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from models import (
    Audit,
    BudgetLine,
    DebtCategory,
    Entity,
    EntityType,
    Extraction,
    FiscalPeriod,
    Loan,
    Severity,
    SourceDocument,
    DocumentType,
)
from services.publication_gate import select_county_pending_bills
from services.county_financial_health import county_audit_signals


@pytest.fixture
def evidence(db_session, seed_country, seed_source_doc):
    counties = []
    for name in ("Mombasa", "Nairobi"):
        e = Entity(
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name=f"{name} County",
            slug=f"{name.lower()}-county",
        )
        db_session.add(e)
        counties.append(e)
    periods = {}
    for year in (2024, 2026):
        p = FiscalPeriod(
            country_id=seed_country.id,
            label=f"FY{year-1}/{str(year)[-2:]}",
            start_date=datetime(year - 1, 7, 1),
            end_date=datetime(year, 6, 30),
        )
        db_session.add(p)
        periods[year] = p
    db_session.flush()
    for e in counties:
        for category, allocation, actual in [
            ("Total", 10_000_000, 5_000_000),
            ("Own Source Revenue", 1_000_000, 400_000),
        ]:
            db_session.add(
                BudgetLine(
                    entity_id=e.id,
                    period_id=periods[2026].id,
                    source_document_id=seed_source_doc.id,
                    category=category,
                    allocated_amount=allocation,
                    actual_spent=actual,
                    currency="KES",
                    page_ref="p.42",
                )
            )
    db_session.flush()
    return counties, periods, seed_source_doc


def stock(db, county, doc, year=2026, amount=1_250_000, **extra):
    row = Loan(
        entity_id=county.id,
        lender=f"Pending Bills {county.slug} {year} evidence {db.query(Loan).count()}",
        debt_category=DebtCategory.PENDING_BILLS,
        principal=amount,
        outstanding=amount,
        currency="KES",
        issue_date=datetime(year, 6, 30),
        source_document_id=doc.id,
        provenance={
            "publication": "cob_cbirr_year_end",
            "category": "county",
            "fiscal_year": f"FY {year-1}/{str(year)[-2:]}",
            "as_at": f"{year}-06-30",
            "source_url": doc.url,
            "table": "Table 2.10",
            "publication_batch": "a" * 64,
            **extra,
        },
    )
    db.add(row)
    db.flush()
    return row


def finding(
    db,
    county,
    period,
    doc,
    *,
    severity=Severity.WARNING,
    role="executives",
    fiscal=None,
    created=2026,
):
    ext = Extraction(
        source_document_id=doc.id,
        page_number=7,
        extractor="synthetic-regression",
        extracted_json={"volume_kind": role, "fiscal_year": fiscal or period.label},
    )
    db.add(ext)
    db.flush()
    row = Audit(
        entity_id=county.id,
        period_id=period.id,
        source_document_id=doc.id,
        extraction_id=ext.id,
        finding_text="A synthetic finding",
        severity=severity,
        page_ref="p.7",
        created_at=datetime(created, 9, 1),
        publishable=True,
    )
    db.add(row)
    db.flush()
    return row


def body(client, path):
    r = client.get(path)
    assert r.status_code == 200, r.text
    return r.json()


def clear():
    from main import clear_all_caches

    clear_all_caches()


def test_current_pending_matches_all_readers_and_retains_history(
    client, db_session, evidence
):
    counties, _, doc = evidence
    old = stock(db_session, counties[0], doc, 2025, 1_000_000)
    stock(db_session, counties[0], doc)
    stock(db_session, counties[1], doc, amount=0)
    listing = body(client, "/api/v1/counties")
    m = next(c for c in listing if c["name"] == "Mombasa")
    assert m["pending_bills"] == 1_250_000
    assert m["pending_bills_as_at"] == "2026-06-30"
    assert m["pending_bills_source"]["url"] == doc.url
    assert body(client, "/api/v1/counties/mombasa-county")["pending_bills"] == 1_250_000
    detail = body(client, "/api/v1/counties/mombasa-county/comprehensive")
    assert detail["debt"]["pending_bills"] == 1_250_000
    assert detail["financial_summary"]["pending_bills_ratio"] == 12.5
    assert detail["financial_summary"]["health_score"] == m["financial_health_score"]
    county = body(client, "/api/v1/pending-bills/counties/mombasa-county")
    assert county["total_pending"] == 1_250_000
    summary = body(client, "/api/v1/pending-bills/summary")
    assert summary["reported_county_sum"] == 1_250_000
    assert summary["coverage"]["county_count"] == 2
    assert summary["coverage"]["county_complete"] is False
    assert summary["total_pending_amount"] is None
    national = body(client, "/api/v1/pending-bills")
    assert national["summary"]["reported_county_sum"] == 1_250_000
    assert len(national["pending_bills"]) == 2
    assert db_session.get(Loan, old.id).outstanding == 1_000_000


def test_incomplete_latest_day_withholds_older_county_everywhere(
    client, db_session, evidence
):
    counties, _, doc = evidence
    stock(db_session, counties[0], doc, 2025, 1_000_000)
    stock(db_session, counties[1], doc, amount=0)
    listing = body(client, "/api/v1/counties")
    m = next(c for c in listing if c["name"] == "Mombasa")
    assert m["pending_bills"] is None
    assert m["pending_bills_absence"] is None
    assert (
        m["pending_bills_selection"]["absent_reason"] == "not_reported_at_latest_date"
    )
    assert m["pending_bills_selection"]["as_at"] == "2026-06-30"
    assert body(client, "/api/v1/counties/mombasa-county")["pending_bills"] is None
    assert (
        body(client, "/api/v1/counties/mombasa-county/comprehensive")["debt"][
            "pending_bills"
        ]
        is None
    )
    assert (
        body(client, "/api/v1/pending-bills/counties/mombasa-county")["total_pending"]
        is None
    )
    summary = body(client, "/api/v1/pending-bills/summary")
    assert summary["reported_county_sum"] == 0
    assert summary["coverage"]["county_count"] == 1
    assert (
        summary["coverage"]["county_absent_reasons"]["Mombasa County"]
        == "not_reported_at_latest_date"
    )


@pytest.mark.parametrize(
    "conflict",
    ["amount", "source_url", "publication_batch", "reader_notes", "fiscal_year"],
)
def test_same_date_conflicts_are_explicit_not_added_or_id_selected(
    client, db_session, evidence, conflict
):
    counties, _, doc = evidence
    stock(db_session, counties[0], doc)
    changes = {
        "amount": {"amount": 2_000_000},
        "source_url": {"source_url": "https://cob.go.ke/other.pdf"},
        "publication_batch": {"publication_batch": "b" * 64},
        "reader_notes": {"reader_notes": [{"code": "assembly_not_printed"}]},
        "fiscal_year": {"fiscal_year": "FY2024/25"},
    }
    stock(db_session, counties[0], doc, **changes[conflict])
    c = body(client, "/api/v1/pending-bills/counties/mombasa-county")
    assert c["total_pending"] is None
    assert c["selection"]["absent_reason"] == "conflicting_same_date_pending_sources"
    d = body(client, "/api/v1/counties/mombasa-county/comprehensive")
    assert d["debt"]["pending_bills"] is None
    assert (
        d["debt"]["pending_bills_selection"]["absent_reason"]
        == "conflicting_same_date_pending_sources"
    )
    summary = body(client, "/api/v1/pending-bills/summary")
    # No surviving row is not a reported zero; coverage still explains the conflict.
    assert summary["reported_county_sum"] is None
    assert (
        summary["coverage"]["county_absent_reasons"]["Mombasa County"]
        == "conflicting_same_date_pending_sources"
    )


def test_equivalent_duplicate_is_idempotent_and_qualification_preserved(
    client, db_session, evidence
):
    counties, _, doc = evidence
    for _ in range(2):
        stock(
            db_session,
            counties[0],
            doc,
            reader_notes=[{"code": "assembly_not_printed", "amount": 1250000}],
        )
    c = body(client, "/api/v1/counties/mombasa-county/comprehensive")
    assert c["debt"]["pending_bills"] == 1_250_000
    assert c["debt"]["pending_bills_notes"] == [
        {"code": "assembly_not_printed", "amount": 1250000}
    ]
    assert (
        body(client, "/api/v1/pending-bills/summary")["coverage"]["county_count"] == 1
    )


def test_latest_missing_amount_does_not_restore_old_stock(client, db_session, evidence):
    counties, _, doc = evidence
    stock(db_session, counties[0], doc, 2025, 1_000_000)
    stock(db_session, counties[0], doc, amount=-1)
    c = body(client, "/api/v1/counties/mombasa-county/comprehensive")
    assert c["debt"]["pending_bills"] is None
    assert (
        c["debt"]["pending_bills_selection"]["absent_reason"]
        == "pending_amount_not_reported"
    )


def test_incompatible_pending_period_withholds_ratio_but_preserves_stock(
    client, db_session, evidence
):
    counties, _, doc = evidence
    stock(db_session, counties[0], doc, 2025, 1_000_000)
    d = body(client, "/api/v1/counties/mombasa-county/comprehensive")
    assert d["debt"]["pending_bills"] == 1_000_000
    assert d["financial_summary"]["pending_bills_ratio"] is None
    assert (
        next(
            c
            for c in d["financial_health"]["unavailable_inputs"]
            if c["name"] == "pending_bills"
        )["reason"]
        == "pending_budget_period_mismatch"
    )
    assert (
        body(client, "/api/v1/counties/mombasa-county")["financial_health_score"]
        == d["financial_summary"]["health_score"]
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_audit_period_and_score_ignore_ingestion_order_and_old_backfill(
    client, db_session, evidence, reverse
):
    counties, periods, doc = evidence
    observations = [
        (periods[2024], Severity.CRITICAL, 2028),
        (periods[2026], Severity.WARNING, 2020),
    ]
    for period, severity, ingested in (
        reversed(observations) if reverse else observations
    ):
        finding(
            db_session, counties[0], period, doc, severity=severity, created=ingested
        )
    d = body(client, "/api/v1/counties/mombasa-county/comprehensive")
    signal = d["financial_health"]["audit_signal"]
    assert signal["severity"] == "warning"
    assert signal["source_period"] == "FY2025/26"
    assert signal["official_opinion"] is False
    assert d["financial_summary"]["health_score"] == 54
    listing = next(
        c for c in body(client, "/api/v1/counties") if c["name"] == "Mombasa"
    )
    assert listing["financial_health_score"] == 54
    assert listing["audit_signal"] == signal
    assert (
        body(client, "/api/v1/counties/mombasa-county")["financial_health_score"] == 54
    )
    finding(
        db_session,
        counties[0],
        periods[2024],
        doc,
        severity=Severity.CRITICAL,
        created=2029,
    )
    clear()
    assert (
        body(client, "/api/v1/counties/mombasa-county/comprehensive")[
            "financial_summary"
        ]["health_score"]
        == 54
    )


def test_multiple_findings_use_maximum_severity_only_in_selected_executive_period(
    client, db_session, evidence
):
    counties, periods, doc = evidence
    finding(db_session, counties[0], periods[2026], doc, severity=Severity.INFO)
    finding(db_session, counties[0], periods[2026], doc, severity=Severity.WARNING)
    finding(
        db_session,
        counties[0],
        periods[2026],
        doc,
        severity=Severity.CRITICAL,
        role="assemblies",
    )
    signal = body(client, "/api/v1/counties/mombasa-county/comprehensive")[
        "financial_health"
    ]["audit_signal"]
    assert signal["severity"] == "warning"
    assert signal["excluded"] == {"county_assembly_excluded": 1}
    finding(db_session, counties[0], periods[2026], doc, severity=Severity.CRITICAL)
    clear()
    assert (
        body(client, "/api/v1/counties/mombasa-county/comprehensive")[
            "financial_health"
        ]["audit_signal"]["severity"]
        == "critical"
    )


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("period", "conflicting_audit_period"),
        ("scope", "missing_or_conflicting_audit_institution"),
    ],
)
def test_latest_conflict_withholds_signal_without_falling_back(
    client, db_session, evidence, kind, reason
):
    counties, periods, doc = evidence
    finding(db_session, counties[0], periods[2024], doc)
    finding(
        db_session,
        counties[0],
        periods[2026],
        doc,
        role=None if kind == "scope" else "executives",
        fiscal="FY2023/24" if kind == "period" else None,
    )
    d = body(client, "/api/v1/counties/mombasa-county/comprehensive")
    signal = d["financial_health"]["audit_signal"]
    assert signal["status"] == "pending"
    assert signal["absent_reason"] == reason
    assert (
        next(
            c
            for c in d["financial_health"]["unavailable_inputs"]
            if c["name"] == "audit_opinion"
        )["reason"]
        == reason
    )


def test_audit_selection_query_count_is_constant_and_has_no_finding_text_projection(
    db_session, evidence
):
    counties, periods, doc = evidence
    for e in counties:
        for _ in range(8):
            finding(db_session, e, periods[2026], doc)
    statements = []

    def record(_conn, _cursor, sql, *_):
        statements.append(sql)

    event.listen(db_session.bind, "before_cursor_execute", record)
    try:
        from main import _audit_is_display_grade

        signals = county_audit_signals(
            db_session, [e.id for e in counties], display_grade=_audit_is_display_grade
        )
    finally:
        event.remove(db_session.bind, "before_cursor_execute", record)
    assert len(statements) == 2
    assert all(s["severity"] == "warning" for s in signals.values())
    assert "finding_text" not in statements[0].split("FROM")[0]


@pytest.mark.parametrize(
    "amount", [True, False, float("nan"), float("inf"), float("-inf"), -1, None]
)
def test_hostile_amounts_cannot_publish_stock(amount):
    def row(year, value):
        return SimpleNamespace(
            entity=SimpleNamespace(type=EntityType.COUNTY),
            debt_category=DebtCategory.PENDING_BILLS,
            provenance={
                "publication": "cob_cbirr_year_end",
                "category": "county",
                "as_at": f"{year}-06-30",
            },
            outstanding=value,
            principal=value,
        )

    result = select_county_pending_bills([row(2025, 100), row(2026, amount)])
    assert result["amount"] is None
    assert result["absent_reason"] == "pending_amount_not_reported"


@pytest.mark.parametrize("currency", ["USD", ""])
def test_non_kes_stock_cannot_enter_kes_balance_or_ratio(
    client, db_session, evidence, currency
):
    counties, _, doc = evidence
    row = stock(db_session, counties[0], doc)
    row.currency = currency
    db_session.flush()
    d = body(client, "/api/v1/counties/mombasa-county/comprehensive")
    assert d["debt"]["pending_bills"] is None
    assert (
        d["debt"]["pending_bills_selection"]["absent_reason"]
        == "unsupported_pending_currency"
    )
    assert d["financial_summary"]["pending_bills_ratio"] is None
    assert (
        body(client, "/api/v1/pending-bills/counties/mombasa-county")["selection"][
            "absent_reason"
        ]
        == "unsupported_pending_currency"
    )


@pytest.mark.parametrize("stats", [None, [], "malformed"])
def test_malformed_optional_source_stats_do_not_crash_endpoint(
    client, db_session, evidence, stats
):
    counties, periods, doc = evidence
    doc.meta = {"extraction_stats": stats}
    finding(db_session, counties[0], periods[2026], doc)
    assert (
        body(client, "/api/v1/counties/mombasa-county/comprehensive")[
            "financial_health"
        ]["audit_signal"]["severity"]
        == "warning"
    )


@pytest.mark.parametrize("serialized", [False, True])
def test_extraction_shape_cannot_bypass_period_conflict(
    client, db_session, evidence, serialized
):
    import json

    counties, periods, doc = evidence
    row = finding(db_session, counties[0], periods[2026], doc, fiscal="FY2023/24")
    if serialized:
        ext = db_session.get(Extraction, row.extraction_id)
        ext.extracted_json = json.dumps(ext.extracted_json)
        db_session.flush()
    assert (
        body(client, "/api/v1/counties/mombasa-county/comprehensive")[
            "financial_health"
        ]["audit_signal"]["absent_reason"]
        == "conflicting_audit_period"
    )


def test_assembly_period_conflict_does_not_poison_executive_signal(
    client, db_session, evidence
):
    counties, periods, doc = evidence
    finding(db_session, counties[0], periods[2026], doc)
    finding(
        db_session,
        counties[0],
        periods[2026],
        doc,
        role="assemblies",
        fiscal="FY2023/24",
        severity=Severity.CRITICAL,
    )
    s = body(client, "/api/v1/counties/mombasa-county/comprehensive")[
        "financial_health"
    ]["audit_signal"]
    assert s["severity"] == "warning"
    assert s["excluded"] == {"county_assembly_excluded": 1}


def test_unknown_period_is_disclosed_and_known_period_date_conflict_withholds_latest(
    client, db_session, evidence
):
    counties, periods, doc = evidence
    finding(db_session, counties[0], periods[2024], doc)
    periods[2026].label = "unknown"
    finding(db_session, counties[0], periods[2026], doc)
    db_session.flush()
    s = body(client, "/api/v1/counties/mombasa-county/comprehensive")[
        "financial_health"
    ]["audit_signal"]
    assert s["source_period"] == "FY2023/24"
    assert s["excluded"] == {"missing_or_ambiguous_audit_period": 1}
    periods[2026].label = "FY2025/26"
    periods[2026].end_date = datetime(2026, 3, 31)
    db_session.add(periods[2026])
    db_session.flush()
    clear()
    s = body(client, "/api/v1/counties/mombasa-county/comprehensive")[
        "financial_health"
    ]["audit_signal"]
    assert s["status"] == "pending"
    assert s["source_period"] == "FY2025/26"
    assert s["absent_reason"] == "missing_or_ambiguous_audit_period"


def test_pending_conflict_evidence_payload_is_bounded():
    def row(index):
        return SimpleNamespace(
            entity=SimpleNamespace(type=EntityType.COUNTY),
            debt_category=DebtCategory.PENDING_BILLS,
            currency="KES",
            provenance={
                "publication": "cob_cbirr_year_end",
                "category": "county",
                "as_at": "2026-06-30",
                "source_url": f"https://cob.go.ke/report-{index}.pdf",
            },
            outstanding=index,
            principal=index,
            source_document_id=index,
        )

    result = select_county_pending_bills([row(i) for i in range(25)])
    assert result["amount"] is None
    assert result["absent_reason"] == "conflicting_same_date_pending_sources"
    assert len(result["sources"]) == 20
    assert result["source_count"] == 25
    assert result["sources_truncated"] is True


def test_pending_reporting_date_is_a_single_metadata_query(db_session, evidence):
    from services.publication_gate import county_pending_reporting_date

    counties, _, doc = evidence
    for e in counties:
        stock(db_session, e, doc, 2025, 1_000_000)
        stock(db_session, e, doc)
    statements = []

    def record(_conn, _cursor, sql, *_):
        statements.append(sql)

    event.listen(db_session.bind, "before_cursor_execute", record)
    try:
        assert county_pending_reporting_date(db_session) == "2026-06-30"
    finally:
        event.remove(db_session.bind, "before_cursor_execute", record)
    assert len(statements) == 1
    assert "provenance" in statements[0].split("FROM")[0]
    assert "outstanding" not in statements[0].split("FROM")[0]


def test_pending_summary_reader_has_constant_queries_in_a_fresh_session(
    db_session, evidence
):
    from sqlalchemy.orm import Session
    from main import _published_pending_bills

    counties, _, doc = evidence
    for e in counties:
        stock(db_session, e, doc, 2025, 1_000_000)
        stock(db_session, e, doc)
    statements = []

    def record(_conn, _cursor, sql, *_):
        statements.append(sql)

    event.listen(db_session.bind, "before_cursor_execute", record)
    try:
        # Unlike the writer fixture session, this identity map contains no
        # entities and cannot hide a lazy per-county relationship lookup.
        with Session(bind=db_session.connection()) as fresh:
            rows, totals = _published_pending_bills(fresh)
    finally:
        event.remove(db_session.bind, "before_cursor_execute", record)
    assert len(statements) == 2
    assert len(rows) == 2
    assert totals["reported_county_sum"] == 2_500_000


@pytest.mark.parametrize("label", ["FY0000/01", "FY0000/0001", "FY9999/00"])
def test_unrepresentable_audit_year_does_not_break_county_readers(
    client, db_session, evidence, label
):
    counties, periods, doc = evidence
    malformed = periods[2024]
    malformed.label = label
    finding(db_session, counties[0], malformed, doc, severity=Severity.CRITICAL)
    db_session.flush()

    def signals():
        clear()
        listing = next(
            c for c in body(client, "/api/v1/counties") if c["name"] == "Mombasa"
        )
        detail = body(client, "/api/v1/counties/mombasa-county")
        comprehensive = body(client, "/api/v1/counties/mombasa-county/comprehensive")
        return [
            listing["audit_signal"],
            detail["audit_signal"],
            comprehensive["financial_health"]["audit_signal"],
        ]

    for signal in signals():
        assert signal["severity"] is None
        assert signal["period_end"] is None
        assert signal["absent_reason"] == "missing_or_ambiguous_audit_period"
        assert signal["excluded"] == {"missing_or_ambiguous_audit_period": 1}

    finding(db_session, counties[0], periods[2026], doc)
    for signal in signals():
        assert signal["severity"] == "warning"
        assert signal["source_period"] == "FY2025/26"
        assert signal["excluded"] == {"missing_or_ambiguous_audit_period": 1}


@pytest.mark.parametrize(
    "label,start,end",
    [("FY0001/02", 1, 2), ("FY0099/00", 99, 100), ("FY9998/99", 9998, 9999)],
)
def test_representable_boundary_audit_years_remain_publishable(
    client, db_session, evidence, label, start, end
):
    counties, periods, doc = evidence
    period = periods[2024]
    period.label = label
    period.start_date = datetime(start, 7, 1)
    period.end_date = datetime(end, 6, 30)
    finding(db_session, counties[0], period, doc)
    db_session.flush()
    listing = next(
        c for c in body(client, "/api/v1/counties") if c["name"] == "Mombasa"
    )
    detail = body(client, "/api/v1/counties/mombasa-county")
    comprehensive = body(client, "/api/v1/counties/mombasa-county/comprehensive")
    for signal in (
        listing["audit_signal"],
        detail["audit_signal"],
        comprehensive["financial_health"]["audit_signal"],
    ):
        assert signal["severity"] == "warning"
        assert signal["period_end"] == datetime(end, 6, 30).date().isoformat()
        assert signal["source_period"] == label
        assert signal["excluded"] == {}


@pytest.mark.parametrize(
    "label,expected",
    [
        ("FY0000/01", None),
        ("FY0000/0001", None),
        ("FY9999/00", None),
        ("FY9999/10000", None),
        ("FY9999/9999", None),
        ("FY9998/99", (9998, 9999)),
        ("FY9998/9999", (9998, 9999)),
        ("FY0001/02", (1, 2)),
        ("FY0001/0002", (1, 2)),
        ("FY0099/00", (99, 100)),
        ("FY1999/00", (1999, 2000)),
        ("FY2025/26", (2025, 2026)),
    ],
)
def test_audit_and_pending_year_boundaries_agree(label, expected):
    from services.county_financial_health import fiscal_year
    from services.publication_gate import pending_period_compatible

    assert fiscal_year(label) == expected
    start, end = expected or (2025, 2026)
    period = {
        "start_date": datetime(start, 7, 1).date().isoformat(),
        "end_date": datetime(end, 6, 30).date().isoformat(),
    }
    assert pending_period_compatible(period["end_date"], label, period) is bool(expected)
    # Unrepresentable denominator dates must also be rejected without a crash.
    assert not pending_period_compatible(
        "0001-06-30", label, {"start_date": "0000-07-01", "end_date": "0001-06-30"}
    )
    assert not pending_period_compatible(
        "10000-06-30", label, {"start_date": "9999-07-01", "end_date": "10000-06-30"}
    )
