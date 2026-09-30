"""The pending-bills fallback asserted three things it had never measured.

``/api/v1/pending-bills/summary`` falls back to the ``loans`` table whenever
``pending_bills`` is empty — which is the live path in production
(``data_source: "loans_table_fallback"``). That fallback published three
figures the loans table cannot support.

**1. Aging.** ::

    "aging_buckets": {"0-30d": 0, "31-90d": 0, "91-180d": 0, "180d+": total}

A ``loans`` row carries no aging column. The literal above states that 100% of
KSh 1.108 **trillion** is more than 180 days overdue — the most alarming
reading available — on the strength of no data whatsoever. Whoever writes the
cheque, the difference between a bill 20 days old and one 400 days old is the
difference between routine and a default, and this asserted the second for all
of it. The same literal is written again on the per-county fallback, where the
debt page's disclaimer never appears.

**2. Bill type.** The type was keyword-matched off the *lender* string, with an
unconditional ``else: bt = "supplier_arrears"``. Nothing in the register's
lender strings matches "salary"/"pension"/"statutory"/"court", so production
reported 100% supplier arrears — a finding about the composition of Kenya's
arrears that is really a statement about a dictionary having no matches.

**3. Trend.** Fiscal-year keys were taken verbatim from provenance with no
normalisation, so production drew ONE year as two points::

    "FY 2024/25"  702.8Bn
    "FY2024/25"   405.4Bn

A reader sees a year that halved. The two sum to 1,108.2Bn — the total — so
they are one year written twice, and the chart's own total contradicts the
total printed above it.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from models import DebtCategory, Entity, EntityType, Loan


def summary(client) -> dict:
    from main import clear_all_caches

    clear_all_caches()
    return client.get("/api/v1/pending-bills/summary").json()


@pytest.fixture()
def national_entity(db_session, seed_country):
    entity = Entity(
        id=902,
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="National Government",
        slug="national-government",
    )
    db_session.add(entity)
    db_session.commit()
    return entity


@pytest.fixture()
def county_entity(db_session, seed_country):
    entity = Entity(
        id=903,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Mombasa County",
        slug="mombasa-county",
    )
    db_session.add(entity)
    db_session.commit()
    return entity


def _bill(entity, doc, lender, amount, fiscal_year, day, as_at="2025-06-30"):
    # A row is published only when it declares the publication for its side:
    # the Treasury BROP for a national line (#265), the Controller of Budget's
    # year-end report for a county (#238)
    # (services.publication_gate.pending_bills_row_is_published). These
    # fixtures stand for such rows, so they say so — and the day they are a
    # stock on, which the total and the trend require to be one day.
    county = entity.type == EntityType.COUNTY
    provenance = {
        "fiscal_year": fiscal_year,
        "publication": "cob_cbirr_year_end" if county else "treasury_brop",
        "category": "county" if county else "mda",
        "as_at": as_at,
    }
    return Loan(
        entity_id=entity.id,
        lender=lender,
        debt_category=DebtCategory.PENDING_BILLS,
        principal=amount,
        outstanding=amount,
        issue_date=datetime(2025, 1, day, tzinfo=timezone.utc),
        currency="KES",
        source_document_id=doc.id,
        provenance=provenance,
    )


@pytest.fixture()
def production_bills(db_session, national_entity, county_entity, seed_source_doc):
    """The two rows behind production's 1,108.2Bn, with its two FY spellings."""
    B = 1e9
    db_session.add_all([
        _bill(national_entity, seed_source_doc,
              "Pending Bills — National Government", 702.8 * B, "FY 2024/25", 1),
        _bill(county_entity, seed_source_doc,
              "Pending Bills — County Governments", 405.4045 * B, "FY2024/25", 2),
    ])
    db_session.commit()
    return db_session


@pytest.fixture()
def complete_publication(db_session, seed_country, national_entity, county_entity):
    """Synthetic full population for aggregate and fiscal-label controls.

    Preserve the historical test amounts and FY spellings, but write the
    complete national pair and all 47 counties through the production writer.
    The extra test-only zeros are not assertions about real county figures.
    """
    from decimal import Decimal
    from seeding.domains.pending_bills.parser import PendingBillRecord
    from seeding.domains.pending_bills.writer import write_pending_bills
    from seeding.pdf_parsers import KENYAN_COUNTIES

    db_session.add_all([
        Entity(country_id=seed_country.id, type=EntityType.COUNTY,
               canonical_name=f"{name} County", slug=f"test-{name.lower()}")
        for name in KENYAN_COUNTIES if name != "Mombasa"
    ])
    db_session.flush()
    national = [
        PendingBillRecord(f"National Government — {category}", "national", category,
                          "FY 2024/25", Decimal(amount), as_at="2025-06-30")
        for category, amount in [("mda", 702_800_000_000), ("state_corporation", 0)]
    ]
    counties = [
        PendingBillRecord(f"{name} County", "county", "county", "FY2024/25",
                          Decimal(405_404_500_000 if name == "Mombasa" else 0), as_at="2025-06-30")
        for name in KENYAN_COUNTIES
    ]
    for records, publication, source in [
        (national, "treasury_brop", "https://treasury.go.ke/test-brop.pdf"),
        (counties, "cob_cbirr_year_end", "https://cob.go.ke/test-cbirr.pdf"),
    ]:
        write_pending_bills(db_session, records, publication=publication,
                            source_url=source, source_title=f"Synthetic {publication}")
    db_session.commit()
    return db_session


# ── 1. Aging ───────────────────────────────────────────────────────────────

def test_aging_is_withheld_because_the_loans_table_has_no_aging_column(
    client, production_bills
):
    body = summary(client)
    assert body["data_source"] == "loans_table_fallback"
    assert body["aging_buckets"] is None
    assert body["aging_buckets_absent_reason"] == "loans_table_carries_no_aging_data"


def test_no_bucket_claims_the_whole_total(client, production_bills):
    """The specific production assertion: 100% of the money in ``180d+``."""
    body = summary(client)
    buckets = body["aging_buckets"] or {}
    total = body["total_pending_amount"]
    assert not any(
        v == pytest.approx(total) for v in buckets.values()
    ), f"a bucket still claims the entire {total / 1e9:.1f}Bn: {buckets}"


def test_the_county_fallback_withholds_aging_too(client, production_bills):
    """The county pages carry no disclaimer, so this path mattered most."""
    from main import clear_all_caches

    clear_all_caches()
    body = client.get("/api/v1/pending-bills/counties/mombasa-county").json()
    assert body["data_source"] == "loans_table_fallback"
    assert body["total_pending"] == pytest.approx(405.4045e9)
    assert body["aging_buckets"] is None
    assert body["aging_buckets_absent_reason"] == "loans_table_carries_no_aging_data"


# ── 2. Bill type ───────────────────────────────────────────────────────────

def test_unmatched_rows_are_not_declared_supplier_arrears(client, production_bills):
    """Neither production lender string says anything about a supplier."""
    body = summary(client)
    assert "supplier_arrears" not in body["breakdown_by_type"]
    assert body["breakdown_by_type"]["unclassified"] == pytest.approx(1108.2045e9)
    assert body["breakdown_by_type_absent_reason"] == (
        "loans_table_carries_no_bill_type"
    )


def test_the_county_fallback_does_not_declare_supplier_arrears_either(
    client, production_bills
):
    from main import clear_all_caches

    clear_all_caches()
    body = client.get("/api/v1/pending-bills/counties/mombasa-county").json()
    assert "supplier_arrears" not in body["breakdown_by_type"]
    assert body["breakdown_by_type"]["unclassified"] == pytest.approx(405.4045e9)


def test_a_lender_string_that_really_does_name_a_type_still_classifies(
    client, db_session, national_entity, seed_source_doc
):
    """Positive control. The keyword match is weak evidence, not no evidence —
    withholding everything would be the opposite failure."""
    B = 1e9
    db_session.add_all([
        _bill(national_entity, seed_source_doc,
              "Pending Bills — Salary Arrears", 100.0 * B, "FY2024/25", 3),
        _bill(national_entity, seed_source_doc,
              "Pending Bills — Court Awards", 50.0 * B, "FY2024/25", 4),
        _bill(national_entity, seed_source_doc,
              "Pending Bills — National Government", 25.0 * B, "FY2024/25", 5),
    ])
    db_session.commit()

    body = summary(client)
    assert body["breakdown_by_type"]["salary"] == pytest.approx(100.0 * B)
    assert body["breakdown_by_type"]["court_awards"] == pytest.approx(50.0 * B)
    assert body["breakdown_by_type"]["unclassified"] == pytest.approx(25.0 * B)
    # Something was classified, so the block is not wholly absent.
    assert body["breakdown_by_type_absent_reason"] is None


# ── 3. Trend ───────────────────────────────────────────────────────────────

def test_one_fiscal_year_is_one_point(client, complete_publication):
    """"FY 2024/25" and "FY2024/25" are the same year."""
    trend = summary(client)["trend"]
    years = [p["year"] for p in trend]
    assert len(years) == len(set(years)), f"duplicate years: {years}"
    assert years == ["FY2024/25"]
    assert trend[0]["total_amount"] == pytest.approx(1108.2045e9)


def test_the_trend_adds_up_to_the_total_printed_above_it(client, complete_publication):
    body = summary(client)
    assert body["total_pending_amount"] == pytest.approx(1108.2045e9)
    assert body["trend_absent_reason"] is None
    assert sum(p["total_amount"] for p in body["trend"]) == pytest.approx(
        body["total_pending_amount"]
    )


def test_distinct_years_stay_distinct():
    """Positive control: normalisation must not collapse real years together,
    nor fold a sub-period into its parent year."""
    from main import _normalised_fiscal_year

    # Exercise the production normalizer directly: different stock editions
    # must not be combined merely to manufacture a multi-year chart fixture.
    labels = ["FY 2023/24", "FY2024/25", "FY 2025/26 Q1"]
    assert [_normalised_fiscal_year(label) for label in labels] == [
        "FY2023/24", "FY2024/25", "FY2025/26 Q1"
    ]


def test_incomplete_historical_rows_cannot_form_a_trend(client, production_bills):
    body = summary(client)
    assert body["total_pending_amount"] is None
    assert body["trend"] == []
    assert body["trend_absent_reason"] == "incomplete_national_publication"


def test_an_unparseable_fiscal_label_is_dropped_not_crashed(
    client, db_session, complete_publication
):
    """``normalize_fiscal_label`` raises on junk; a junk label must not take
    the endpoint down, and must not be silently merged into a real year."""
    loan = next(row for row in db_session.query(Loan).all()
                if row.provenance.get("category") == "mda")
    loan.provenance = {**loan.provenance, "fiscal_year": "not a fiscal year"}
    db_session.commit()

    body = summary(client)
    assert body["status"] == "success"
    assert [p["year"] for p in body["trend"]] == ["FY2024/25"]
    assert body["trend"][0]["total_amount"] == pytest.approx(405.4045e9)
    assert body["trend_unattributed_amount"] == pytest.approx(702.8e9)
    assert body["total_pending_amount"] == pytest.approx(
        body["trend"][0]["total_amount"] + body["trend_unattributed_amount"]
    )


def test_the_county_path_infers_from_rows_it_actually_read(
    client, db_session, county_entity, seed_source_doc
):
    """The county breakdown is not a label stuck on a scalar.

    Pre-fix it was ``{"supplier_arrears": total} if total else {}`` — built
    from ONE summed number, with no per-bill data consulted at all. That is a
    fabricated category rather than a misclassification: there was nothing in
    the expression that could ever have produced a different answer.

    Post-fix the county path reads the same per-row ``Loan.lender`` strings the
    national path reads, filtered to one entity, so a row that names its type
    classifies on the county page exactly as it does nationally — and a row
    that does not is ``unclassified`` rather than assumed.
    """
    from main import clear_all_caches

    B = 1e9
    db_session.add_all([
        _bill(county_entity, seed_source_doc,
              "Pending Bills — Salary Arrears (Mombasa County)", 30.0 * B,
              "FY2024/25", 11),
    ])
    db_session.commit()

    clear_all_caches()
    body = client.get("/api/v1/pending-bills/counties/mombasa-county").json()

    assert body["breakdown_by_type"]["salary"] == pytest.approx(30.0 * B)
    assert "unclassified" not in body["breakdown_by_type"]
    assert "supplier_arrears" not in body["breakdown_by_type"]
    # Something was classified, so the block is not wholly absent.
    assert body["breakdown_by_type_absent_reason"] is None
    # And the parts still sum to the total printed beside them.
    assert sum(body["breakdown_by_type"].values()) == pytest.approx(
        body["total_pending"]
    )
