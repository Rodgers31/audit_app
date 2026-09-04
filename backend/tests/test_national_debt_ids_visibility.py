"""A silent fallback to the fixture must not look like a healthy run.

On the 2026-09-04 nightly the IDS creditor replacement did not apply. It left
NO trace: no log line, and nothing in the payload metadata. The run reported
`national_debt: data source = LIVE` and committed 15 records, so from the
outside it was indistinguishable from a run that had replaced the external
book with 42 IDS creditors.

That matters because the fixture's external rows are the ones this module's
own comment records as overstating the book — Eurobonds 2,276Bn against IDS's
858Bn. Falling back to them is a material change in what the site publishes,
and it was invisible.
"""

import seeding.domains.national_debt.fetcher as fetcher


class _Payload(dict):
    pass


def _fixture_payload():
    return {
        "metadata": {},
        "loans": [
            {
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": "Eurobonds (2014, 2018, 2019, 2021, 2024 issues)",
                "debt_category": "external_commercial",
                "principal": "2276000000000.00",
                "outstanding": "2276000000000.00",
                "currency": "KES",
            }
        ],
    }


def _stub_everything(monkeypatch, *, creditors):
    """Neutralise every network step except the creditor pull under test."""
    monkeypatch.setattr(fetcher, "load_json_resource", lambda **k: _fixture_payload())
    monkeypatch.setattr(
        fetcher, "fetch_external_debt_from_wb_ids", lambda *a, **k: []
    )
    monkeypatch.setattr(fetcher, "fetch_external_creditors", creditors)
    for name in (
        "fetch_cbk_domestic_debt",
        "fetch_treasury_bond_register",
        "fetch_public_debt_monthly",
    ):
        if hasattr(fetcher, name):
            monkeypatch.setattr(fetcher, name, lambda *a, **k: [])


class _Settings:
    national_debt_dataset_url = "file://x.json"
    live_pdf_fetch_enabled = True


def test_a_skipped_replacement_is_recorded_in_the_payload(monkeypatch):
    """The regression: this used to leave no trace at all."""
    _stub_everything(monkeypatch, creditors=lambda *a, **k: None)
    payload = fetcher.fetch_debt_payload(object(), _Settings())
    meta = payload.get("metadata", {})
    assert meta.get("ids_creditor_replacement_applied") is False
    assert meta.get("ids_creditor_skip_reason") == "returned_no_creditors"


def test_a_raising_pull_records_the_exception_not_just_a_warning(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("WB unreachable")

    _stub_everything(monkeypatch, creditors=_boom)
    payload = fetcher.fetch_debt_payload(object(), _Settings())
    meta = payload.get("metadata", {})
    assert meta.get("ids_creditor_replacement_applied") is False
    assert "RuntimeError" in meta.get("ids_creditor_skip_reason", "")
    assert "WB unreachable" in meta.get("ids_creditor_skip_reason", "")


def test_a_successful_replacement_still_reports_applied(monkeypatch):
    """NEGATIVE CONTROL — the flag must be able to say True."""
    _stub_everything(
        monkeypatch,
        creditors=lambda *a, **k: {
            "year": 2024,
            "creditors": [object(), object()],
            "coverage": {"status": "within_band"},
            "loans": [],
        },
    )
    payload = fetcher.fetch_debt_payload(object(), _Settings())
    meta = payload.get("metadata", {})
    assert meta.get("ids_creditor_replacement_applied") is True
    assert meta.get("ids_creditor_year") == 2024
    assert "ids_creditor_skip_reason" not in meta
