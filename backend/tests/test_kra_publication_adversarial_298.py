"""Independent executable adversarial checks for the #298 publication fix."""

import copy
import gzip
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from seeding.domains.revenue_by_source.fetcher import _overlay_kra_release, _stamp_published
from seeding.domains.revenue_by_source.kra_discovery import parse_dashboard_bundle, validate_release
from seeding.domains.revenue_by_source.parser import parse_revenue_payload
from seeding.domains.revenue_by_source.writer import _apply_updates
from services.revenue_publication import revenue_source_row

PAGE = "https://www.kra.go.ke/annual-revenue-performance-fy-2025-2026"
BUNDLE = "https://krarevenue2526testingdashboard.bolt.host/assets/index-n9eGcpF_.js"


def _release():
    fixture = Path(__file__).parent / "fixtures/kra/fy2025_26_dashboard_bundle.js.gz"
    with gzip.open(fixture, "rt") as stream:
        release = parse_dashboard_bundle(stream.read(), url=PAGE, data_url=BUNDLE)
    release.retrieved_at = "2026-09-27T00:00:00+00:00"
    release.content_sha256 = "f3cf2fd1075f4af3eb0aafb92ed6c8a1e336437b2603a9dc67a28283561d03d7"
    return release


def _row(**overrides):
    values = dict(
        revenue_type="PAYE", category="tax", amount_billion_kes=Decimal("598.81"),
        target_billion_kes=None, performance_pct=None, yoy_growth_pct=None,
        share_of_total_pct=None, source_document_id=7,
        meta={"basis": "published", "source": {"url": PAGE, "stated_amount_billion_kes": "598.807"}},
    )
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize("value", [True, False, Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), Decimal("-1")])
def test_publication_does_not_emit_invalid_amount(value):
    result = revenue_source_row(_row(amount_billion_kes=value))
    assert result["amount"] is None


def test_publication_preserves_publisher_reported_zero():
    assert revenue_source_row(_row(amount_billion_kes=Decimal("0")))["amount"] == 0


@pytest.mark.parametrize("value", [True, False, Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), Decimal("-1")])
def test_new_agency_measure_is_validated_before_publication(value):
    release = _release()
    release.agency_bn = value
    assert validate_release(release), f"invalid agency figure accepted: {value!r}"


def test_head_validation_preserves_an_explicit_zero():
    release = _release()
    release.heads["Excise Duty"].amount_bn = Decimal("0")
    assert validate_release(release) == []


def test_factual_agency_measure_and_each_total_keep_own_source_amount():
    release = _release()
    assert release.agency_bn == Decimal("276.139")
    payload, _ = _overlay_kra_release([], release)
    records = parse_revenue_payload(payload)
    expected = {
        "Total KRA Collections": Decimal("2844"),
        "Total Exchequer Revenue": Decimal("2568"),
        "Total Agency Revenue": Decimal("276.139"),
    }
    for record in records:
        if record.revenue_type not in expected:
            continue
        value = expected.pop(record.revenue_type)
        assert record.metadata["source"]["stated_amount_billion_kes"] == str(value)
        assert record.metadata["source"]["data_url"] == BUNDLE
        assert record.metadata["source"]["sha256"] == release.content_sha256
        assert record.metadata["source"]["period"] == "FY 2025/26"
        assert record.metadata["source"]["retrieved_at"] == release.retrieved_at
        assert record.metadata["source"]["publication_date"] is None
    assert not expected


def test_explicit_residual_withdrawal_survives_parser_writer_publication():
    rows, _ = _overlay_kra_release([], _release())
    record = next(r for r in parse_revenue_payload(rows) if r.revenue_type == "Other Tax Revenue")
    row = _row(revenue_type="Other Tax Revenue", amount_billion_kes=Decimal("216.25"), meta={"basis": "residual"})
    assert _apply_updates(row, record, 8)
    assert row.amount_billion_kes is None
    assert row.meta["absent_reason"]
    assert revenue_source_row(row)["amount"] is None


def test_fallback_cannot_attach_projection_provenance_to_retained_actual():
    row = _row()
    original = copy.deepcopy(row)
    record = parse_revenue_payload([{
        "fiscal_year": "FY 2025/26", "revenue_type": "PAYE",
        "basis": "projected", "amount_billion_kes": None,
        "target_billion_kes": 646, "notes": "Projected: historical fixture fallback",
    }])[0]
    _apply_updates(row, record, 8)
    # Retaining a last known actual is reasonable only with its original
    # provenance. An explicit withdrawal is also honest; a hybrid is neither.
    assert row.amount_billion_kes is None or (
        row.meta == original.meta and row.source_document_id == original.source_document_id
    )


def test_unchanged_amount_does_not_keep_an_unrelated_source_document_url():
    old_url = "https://www.kra.go.ke/news-center/press-release/older-edition"
    payload = [{
        "fiscal_year": "FY 2025/26", "revenue_type": "PAYE", "category": "tax",
        "basis": "published", "amount_billion_kes": 598.81,
        "source_url": old_url, "notes": "Previous source with the same rounded amount",
    }]
    rows, _ = _overlay_kra_release(payload, _release())
    row = next(row for row in rows if row["revenue_type"] == "PAYE")
    assert row["source_url"] == row["source"]["url"] == PAGE


def test_revised_amount_refreshes_note_even_within_old_fifty_million_tolerance():
    row = {
        "fiscal_year": "FY 2025/26", "revenue_type": "PAYE", "basis": "published",
        "amount_billion_kes": 598.81, "source_url": PAGE,
        "notes": "KRA collected KES 598.807B",
    }
    _stamp_published(row, 598.837, "KRA collected KES 598.837B", PAGE)
    assert row["amount_billion_kes"] == 598.84
    assert row["notes"] == "KRA collected KES 598.837B"


def test_unavailable_publisher_cannot_write_fixture_over_existing_evidence(monkeypatch):
    from seeding import freshness
    from seeding.domains.revenue_by_source import fetcher

    monkeypatch.setattr(fetcher, "load_json_resource", lambda **kw: [{
        "fiscal_year": "FY 2025/26", "revenue_type": "PAYE",
        "amount_billion_kes": None, "basis": "projected",
    }])
    monkeypatch.setattr(fetcher, "_apply_kra_live", lambda rows, *args: (rows, "no_release_found"))
    settings = SimpleNamespace(enrich_with_worldbank=False, revenue_by_source_dataset_url="fixture")
    freshness.reset("revenue_by_source")
    assert fetcher.fetch_revenue_payload(None, settings) == []
    result = freshness.get("revenue_by_source")
    assert result["mode"] == "partial"
    assert "source_unavailable" in result["reason"]
