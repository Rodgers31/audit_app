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


def _bill(entity, doc, lender, amount, fiscal_year, day):
    return Loan(
        entity_id=entity.id,
        lender=lender,
        debt_category=DebtCategory.PENDING_BILLS,
        principal=amount,
        outstanding=amount,
        issue_date=datetime(2025, 1, day, tzinfo=timezone.utc),
        currency="KES",
        source_document_id=doc.id,
        provenance={"fiscal_year": fiscal_year},
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

def test_one_fiscal_year_is_one_point(client, production_bills):
    """"FY 2024/25" and "FY2024/25" are the same year."""
    trend = summary(client)["trend"]
    years = [p["year"] for p in trend]
    assert len(years) == len(set(years)), f"duplicate years: {years}"
    assert years == ["FY2024/25"]
    assert trend[0]["total_amount"] == pytest.approx(1108.2045e9)


def test_the_trend_adds_up_to_the_total_printed_above_it(client, production_bills):
    body = summary(client)
    assert sum(p["total_amount"] for p in body["trend"]) == pytest.approx(
        body["total_pending_amount"]
    )


def test_distinct_years_stay_distinct(
    client, db_session, national_entity, seed_source_doc
):
    """Positive control: normalisation must not collapse real years together,
    nor fold a sub-period into its parent year."""
    B = 1e9
    db_session.add_all([
        _bill(national_entity, seed_source_doc, "Pending Bills — A",
              100.0 * B, "FY 2023/24", 6),
        _bill(national_entity, seed_source_doc, "Pending Bills — B",
              200.0 * B, "FY2024/25", 7),
        _bill(national_entity, seed_source_doc, "Pending Bills — C",
              300.0 * B, "FY 2025/26 Q1", 8),
    ])
    db_session.commit()

    trend = summary(client)["trend"]
    assert [p["year"] for p in trend] == ["FY2023/24", "FY2024/25", "FY2025/26 Q1"]


def test_an_unparseable_fiscal_label_is_dropped_not_crashed(
    client, db_session, national_entity, seed_source_doc
):
    """``normalize_fiscal_label`` raises on junk; a junk label must not take
    the endpoint down, and must not be silently merged into a real year."""
    B = 1e9
    db_session.add_all([
        _bill(national_entity, seed_source_doc, "Pending Bills — A",
              100.0 * B, "FY2024/25", 9),
        _bill(national_entity, seed_source_doc, "Pending Bills — B",
              50.0 * B, "not a fiscal year", 10),
    ])
    db_session.commit()

    body = summary(client)
    assert body["status"] == "success"
    assert [p["year"] for p in body["trend"]] == ["FY2024/25"]
    assert body["trend"][0]["total_amount"] == pytest.approx(100.0 * B)


# ── 4. The same defect, pointing the other way ─────────────────────────────
#
# Not in the audit's list; found in the same function while fixing the three
# above. The ``pending_bills`` TABLE path (the one the fallback exists for)
# bucketed with ``days = b.aging_days or 0``, so a bill whose age nobody
# recorded was filed under "0-30d" — the most reassuring reading available,
# asserted from a NULL. It is the mirror of the "180d+": total literal.

def test_a_bill_with_no_recorded_age_is_not_declared_brand_new(
    client, db_session, county_entity
):
    from models import BillType, PendingBill

    B = 1e9
    db_session.add_all([
        # (entity, bill_type, fiscal_year) is unique — vary the type.
        PendingBill(entity_id=county_entity.id, bill_type=BillType.SUPPLIER_ARREARS,
                    amount=10.0 * B, fiscal_year="FY2024/25", aging_days=15),
        PendingBill(entity_id=county_entity.id, bill_type=BillType.SALARY,
                    amount=90.0 * B, fiscal_year="FY2024/25", aging_days=None),
    ])
    db_session.commit()

    body = summary(client)
    assert body["data_source"] == "pending_bills_table"
    buckets = body["aging_buckets"]

    assert buckets["0-30d"] == pytest.approx(10.0 * B), (
        "the undated 90Bn is being counted as under a month old"
    )
    assert buckets["unknown"] == pytest.approx(90.0 * B)
    assert sum(buckets.values()) == pytest.approx(body["total_pending_amount"])


def test_the_pending_bills_table_normalises_its_fiscal_years_too(
    client, db_session, county_entity
):
    """``PendingBill``'s natural key is (entity, bill_type, fiscal_year), so
    two spellings of one year survive as two rows there as well."""
    from models import BillType, PendingBill

    B = 1e9
    db_session.add_all([
        PendingBill(entity_id=county_entity.id, bill_type=BillType.SUPPLIER_ARREARS,
                    amount=70.0 * B, fiscal_year="FY 2024/25", aging_days=200),
        PendingBill(entity_id=county_entity.id, bill_type=BillType.SALARY,
                    amount=40.0 * B, fiscal_year="FY2024/25", aging_days=200),
    ])
    db_session.commit()

    body = summary(client)
    assert body["data_source"] == "pending_bills_table"
    assert [p["year"] for p in body["trend"]] == ["FY2024/25"]
    assert body["trend"][0]["total_amount"] == pytest.approx(110.0 * B)


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
        _bill(county_entity, seed_source_doc,
              "Pending Bills — County Governments", 70.0 * B, "FY2024/25", 12),
    ])
    db_session.commit()

    clear_all_caches()
    body = client.get("/api/v1/pending-bills/counties/mombasa-county").json()

    assert body["breakdown_by_type"]["salary"] == pytest.approx(30.0 * B)
    assert body["breakdown_by_type"]["unclassified"] == pytest.approx(70.0 * B)
    assert "supplier_arrears" not in body["breakdown_by_type"]
    # Something was classified, so the block is not wholly absent.
    assert body["breakdown_by_type_absent_reason"] is None
    # And the parts still sum to the total printed beside them.
    assert sum(body["breakdown_by_type"].values()) == pytest.approx(
        body["total_pending"]
    )
