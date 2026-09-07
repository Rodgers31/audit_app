"""A skipped external replacement must not publish, and must not be silent.

On the 2026-09-04 nightly the IDS creditor replacement did not apply. It left
NO trace: no log line, and nothing in the payload metadata. The run reported
`national_debt: data source = LIVE` and committed 15 records, so from the
outside it was indistinguishable from a run that had replaced the external
book with 42 IDS creditors.

That was fixed by recording the skip in the payload — and then the fix was
found to be insufficient, because recording it still PUBLISHED it. What the
fixture's external rows put on the page, measured on a live run with the pull
forced to quarantine:

    external            6,584.7Bn   against 5,465.8 from the gated pull
      Eurobonds           2,276.0Bn   IDS reports ~890Bn      2.6x
      Commercial banks      400.0Bn   IDS reports ~124Bn      3.2x
    HEADLINE                13.34T   against the register's 12.22T

So the gate firing correctly published the worst number in the codebase. The
fetcher now refuses instead: it raises, the domain writes nothing, and the
previous seed's rows stand.
"""

import pytest
import seeding.domains.national_debt.fetcher as fetcher


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
    monkeypatch.setattr(
        fetcher, "fetch_domestic_debt_from_cbk_bulletin", lambda *a, **k: []
    )
    monkeypatch.setattr(
        fetcher,
        "fetch_bond_register",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("not under test")),
    )


class _Settings:
    national_debt_dataset_url = "file://x.json"
    live_pdf_fetch_enabled = True


def test_a_skipped_replacement_refuses_to_publish(monkeypatch):
    """The regression. It used to leave no trace; then it left a trace and
    published anyway. Now it publishes nothing."""
    _stub_everything(monkeypatch, creditors=lambda *a, **k: None)
    with pytest.raises(fetcher.DebtRegisterIncomplete) as exc:
        fetcher.fetch_debt_payload(object(), _Settings())
    assert "returned_no_creditors" in str(exc.value)
    assert "Nothing was written" in str(exc.value)


def test_the_refusal_names_the_exception_that_caused_it(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("WB unreachable")

    _stub_everything(monkeypatch, creditors=_boom)
    with pytest.raises(fetcher.DebtRegisterIncomplete) as exc:
        fetcher.fetch_debt_payload(object(), _Settings())
    assert "RuntimeError" in str(exc.value)
    assert "WB unreachable" in str(exc.value)


def test_the_fixtures_external_rows_never_reach_the_caller(monkeypatch):
    """The money question. 2,276Bn of Eurobonds must not come back out of
    this function when the pull was refused."""
    _stub_everything(monkeypatch, creditors=lambda *a, **k: None)
    try:
        payload = fetcher.fetch_debt_payload(object(), _Settings())
    except fetcher.DebtRegisterIncomplete:
        return
    pytest.fail(
        "the fixture's external rows were returned for publication: "
        f"{[l['lender'] for l in payload['loans']]}"
    )


def test_a_refused_run_is_stale_to_the_freshness_gate(monkeypatch):
    """Refusing must not read as a healthy run.

    ``mark_live`` sits at the end of fetch_debt_payload and is never reached,
    so the domain cannot record a live mode and ``is_stale`` says so. That is
    what the nightly's staleness gate keys on.
    """
    from seeding import freshness

    freshness.reset("national_debt")
    _stub_everything(monkeypatch, creditors=lambda *a, **k: None)
    with pytest.raises(fetcher.DebtRegisterIncomplete):
        fetcher.fetch_debt_payload(object(), _Settings())

    assert freshness.get("national_debt")["mode"] != freshness.LIVE
    assert freshness.is_stale("national_debt") is True


def test_the_refusal_is_recorded_before_the_raise(monkeypatch):
    """Stale is not enough — the record has to say WHY, and say it truthfully.

    Raising before any ``mark_*`` left the mode at "unknown", which the nightly
    then rendered as "served from a FIXTURE ... (reasons: unrecorded)". Both
    halves of that sentence were false: no fixture was served, and the reason
    was sitting in ``job.errors`` the whole time.

    ``mark_fixture`` is deliberately NOT the fix. It would write a false
    statement into the provenance record on a project whose thesis is that the
    provenance record is true.
    """
    from seeding import freshness

    freshness.reset("national_debt")
    _stub_everything(monkeypatch, creditors=lambda *a, **k: None)
    with pytest.raises(fetcher.DebtRegisterIncomplete):
        fetcher.fetch_debt_payload(object(), _Settings())

    recorded = freshness.get("national_debt")
    assert recorded["mode"] == freshness.REFUSED
    assert recorded["mode"] != freshness.FIXTURE
    assert recorded.get("reason"), "a refusal with no recorded reason"
    # The gate that refused, not merely "something refused".
    assert "returned_no_creditors" in (recorded.get("detail") or "")
    freshness.reset("national_debt")


def test_a_published_run_is_not_recorded_as_refused(monkeypatch):
    """NEGATIVE CONTROL. A mode that is always set is not a mode."""
    from seeding import freshness

    freshness.reset("national_debt")
    _stub_everything(
        monkeypatch,
        creditors=lambda *a, **k: {
            "year": 2024,
            "creditors": [object()],
            "coverage": {"status": "within_band"},
            "loans": [
                {
                    "entity_name": "National Government",
                    "entity_type": "national",
                    "lender": "Multilateral (International Monetary Fund)",
                    "debt_category": "external_multilateral",
                    "principal": "668500000000.00",
                    "outstanding": "668500000000.00",
                    "currency": "KES",
                }
            ],
        },
    )
    fetcher.fetch_debt_payload(object(), _Settings())
    assert freshness.get("national_debt")["mode"] != freshness.REFUSED
    freshness.reset("national_debt")


def test_a_refused_run_fails_the_nightly_freshness_gate(db_session):
    """The claim the whole refusal rests on, checked rather than assumed.

    Refusing only beats publishing the fixture if somebody finds out. The CLI
    copies ``source_mode``, ``source_fallback_reason`` and ``source_detail``
    off ``freshness.get()`` onto the job row, so this builds the row the CLI
    would build for a refused run and asserts the nightly both FAILS on it and
    describes it correctly.

    The level alone is not enough. It was already FAIL before the mode existed
    — via the all-fixture branch, whose prose said a fixture had been served
    and the reason was unrecorded. Neither was true.
    """
    from datetime import datetime, timezone

    from models import IngestionJob, IngestionStatus
    from seeding import freshness
    from seeding.staleness import check_ingestion_freshness

    freshness.reset("national_debt")
    freshness.mark_refused(
        "national_debt",
        reason="external_register_incomplete",
        detail="IDS creditor replacement did not apply (returned_no_creditors)",
    )
    provenance = freshness.get("national_debt")
    freshness.reset("national_debt")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db_session.add(
        IngestionJob(
            domain="national_debt",
            status=IngestionStatus.COMPLETED_WITH_ERRORS,
            started_at=now,
            finished_at=now,
            items_processed=0,
            items_created=0,
            items_updated=0,
            errors=["Register refused, nothing written: gate 3 refused the pull"],
            # Exactly the three keys seeding/cli.py writes.
            meta={
                "source_mode": provenance["mode"],
                "source_fallback_reason": provenance["reason"],
                "source_detail": provenance["detail"],
            },
        )
    )
    db_session.commit()

    findings = check_ingestion_freshness(db_session, domains=["national_debt"])
    assert findings, "a refused run left the domain unjudged"
    assert [f.level for f in findings] == ["FAIL"], (
        f"a refused run did not fail the gate: {[(f.level, f.message) for f in findings]}"
    )
    message = findings[0].message
    assert "refused to publish" in message, message
    assert "previous seed" in message, message
    assert "returned_no_creditors" in message, message
    assert "FIXTURE" not in message.upper(), (
        f"the gate still calls a refusal a fixture: {message}"
    )


def test_a_successful_replacement_still_publishes(monkeypatch):
    """NEGATIVE CONTROL — the refusal must be able to not fire."""
    freshness_rows = {
        "year": 2024,
        "creditors": [object(), object()],
        "coverage": {"status": "within_band"},
        "loans": [
            {
                "entity_name": "National Government",
                "entity_type": "national",
                "lender": "Multilateral (International Monetary Fund)",
                "debt_category": "external_multilateral",
                "principal": "668500000000.00",
                "outstanding": "668500000000.00",
                "currency": "KES",
            }
        ],
    }
    _stub_everything(monkeypatch, creditors=lambda *a, **k: freshness_rows)
    payload = fetcher.fetch_debt_payload(object(), _Settings())
    meta = payload.get("metadata", {})
    assert meta.get("ids_creditor_replacement_applied") is True
    assert meta.get("ids_creditor_year") == 2024
    assert "ids_creditor_skip_reason" not in meta
    lenders = [l["lender"] for l in payload["loans"]]
    assert "Eurobonds (2014, 2018, 2019, 2021, 2024 issues)" not in lenders
    assert "Multilateral (International Monetary Fund)" in lenders


def test_the_offline_path_still_serves_the_fixture(monkeypatch):
    """``live_pdf_fetch_enabled=False`` is the declared offline/dev source, not
    a quarantine. It must keep working, or local development breaks."""

    class _Offline(_Settings):
        live_pdf_fetch_enabled = False

    monkeypatch.setattr(fetcher, "load_json_resource", lambda **k: _fixture_payload())
    payload = fetcher.fetch_debt_payload(object(), _Offline())
    assert [l["lender"] for l in payload["loans"]] == [
        "Eurobonds (2014, 2018, 2019, 2021, 2024 issues)"
    ]


def test_the_domain_run_writes_nothing_when_the_register_is_refused(monkeypatch):
    """End to end at the layer that matters: the writer must not be called.

    Yesterday's rows stand. A partial register — refreshed domestic beside a
    stale external half — is not a safer outcome, it is the mixed-basis
    problem in miniature.
    """
    from seeding.domains import national_debt as domain
    from seeding.types import DomainRunContext

    class _NoClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(domain, "create_http_client", lambda settings: _NoClient())
    monkeypatch.setattr(
        domain.fetcher,
        "fetch_debt_payload",
        lambda client, settings: (_ for _ in ()).throw(
            fetcher.DebtRegisterIncomplete("pull refused by gate 3")
        ),
    )

    def _must_not_run(*a, **k):
        raise AssertionError("the writer ran on a refused register")

    monkeypatch.setattr(domain.writer, "write_debt_records", _must_not_run)
    monkeypatch.setattr(domain.parser, "parse_debt_payload", _must_not_run)

    result = domain.run(
        session=object(),
        settings=_Settings(),
        context=DomainRunContext(since=None, dry_run=False, job_id=1),
    )
    assert result.items_created == 0
    assert result.items_updated == 0
    assert result.items_processed == 0
    assert result.errors and "Register refused, nothing written" in result.errors[0]
    assert "pull refused by gate 3" in result.errors[0]
