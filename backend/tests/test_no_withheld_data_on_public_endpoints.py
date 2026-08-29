"""No withheld figure may appear on ANY public endpoint.

Why this test exists
--------------------
Stage 0 gated ``audits`` in ``routers/audit_dashboard.py`` — 13 call sites,
correctly, with passing tests — and Gate 0 passed. It did not gate ``main.py``,
which serves 11 more routes that read ``audits``. ``/api/v1/audits/federal``
went on returning all 25 withheld findings and a ``total_amount_in_findings``
of KES 3,313,000,000,000 — exactly the quarantined sum — and the homepage
prefetches it (``frontend/app/page.tsx:73``).

The defect was not the missed endpoint. It was that the gate was verified at
the endpoint that had been edited rather than at the surface a citizen sees.
So this test does not name endpoints: it enumerates them from the live OpenAPI
schema, so an endpoint added tomorrow is covered by construction.

Structure
---------
* a *dark* sentinel — an audit whose source document has no URL. Must appear
  nowhere, in any numeric rendering.
* a *lit* sentinel — an audit whose source document has a URL. Must appear
  somewhere. Without this the suite would pass vacuously if the enumeration
  found nothing or every route 500'd (``prove-baseline-alive``).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from models import (
    Audit,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    FiscalPeriod,
    Severity,
    SourceDocument,
)

# Distinctive, implausible, and unlikely to collide with real data or with
# an id, count, timestamp or percentage appearing incidentally in a payload.
DARK_AMOUNT = Decimal("987654321.01")  # withheld — must never surface
LIT_AMOUNT = Decimal("123456789.07")  # publishable — must surface somewhere

COUNTY_ID = 900
NATIONAL_ID = 901
COUNTRY_ID = 1

# Routes we cannot meaningfully call. Each needs a reason; the list is asserted
# to stay small so it cannot quietly become "skip everything".
SKIP_PREFIXES = (
    "/api/v1/admin",  # auth-gated; not public
    "/api/v1/auth",  # auth-gated; not public
)


def _representations(amount: Decimal) -> set[str]:
    """Every way a figure might reach a reader.

    A number withheld from ``total`` but leaked through a formatted label is
    still leaked, so match the abbreviations the frontend's ``fmtKES`` emits
    as well as the raw JSON forms.
    """
    f = float(amount)
    out = {
        str(amount),  # 987654321.01
        str(f),  # 987654321.01
        f"{f:.2f}",
        f"{int(f)}",  # 987654321
        f"{int(f):,}",  # 987,654,321
        f"{f:,.2f}",  # 987,654,321.01
    }
    # fmtKES-style abbreviations, at the precisions used across the app
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if f >= div:
            for places in (0, 1, 2, 3):
                out.add(f"{f / div:.{places}f}{suffix}")
                out.add(f"KES {f / div:.{places}f}{suffix}")
    return {s for s in out if len(s) >= 6}  # drop anything too short to be distinctive


def _body_contains(body: str, amount: Decimal) -> str | None:
    """Return the matching representation, or None."""
    # Compare against a comma-stripped copy too, so "987,654,321" is caught
    # even when we only generated the bare digits.
    stripped = body.replace(",", "")
    for rep in _representations(amount):
        if rep in body or rep.replace(",", "") in stripped:
            return rep
    return None


@pytest.fixture()
def sentinels(db_session, seed_country):
    """One withheld audit and one publishable audit, otherwise identical."""
    dark_doc = SourceDocument(
        id=1836,
        country_id=seed_country.id,
        publisher="Office of the Auditor General",
        title="Report of the Auditor General on the National Government FY2023/2024",
        url=None,  # <- the defect: nothing a reader can open
        fetch_date=datetime(2024, 12, 15, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,  # ...yet marked available
    )
    lit_doc = SourceDocument(
        id=2392,
        country_id=seed_country.id,
        publisher="Office of the Auditor-General",
        title="Auditor-General's Report on National Government 2024-2025",
        url="https://www.oagkenya.go.ke/wp-content/uploads/2026/05/national.pdf",
        fetch_date=datetime(2026, 7, 19, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        status=DocumentStatus.AVAILABLE,
    )
    county = Entity(
        id=COUNTY_ID,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nairobi County",
        slug="nairobi-sentinel",
        meta={"county_code": "001"},
    )
    national = Entity(
        id=NATIONAL_ID,
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="National Government of Kenya",
        slug="national-sentinel",
    )
    period = FiscalPeriod(
        id=900,
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    db_session.add_all([dark_doc, lit_doc, county, national, period])
    db_session.flush()

    def mk(entity_id, doc_id, amount, tag):
        return Audit(
            entity_id=entity_id,
            period_id=period.id,
            finding_text=f"{tag} sentinel finding KES {amount}",
            severity=Severity.CRITICAL,
            source_document_id=doc_id,
            query_type="financial_audit",
            amount=amount,
            status="Unresolved",
            audit_opinion="Adverse",
            audit_year=2025,
            # /audits/federal sums provenance[0].amount_involved, not .amount,
            # so the sentinel has to be reachable by both paths.
            provenance=[{"amount_involved": f"{amount}", "status": "pending"}],
        )

    db_session.add_all(
        [
            mk(NATIONAL_ID, dark_doc.id, DARK_AMOUNT, "dark"),
            mk(COUNTY_ID, dark_doc.id, DARK_AMOUNT, "dark"),
            mk(NATIONAL_ID, lit_doc.id, LIT_AMOUNT, "lit"),
            mk(COUNTY_ID, lit_doc.id, LIT_AMOUNT, "lit"),
        ]
    )
    db_session.commit()


def _public_get_routes(client):
    """Every public GET route, from the live schema — never a hand-kept list.

    A hand-maintained list leaves the next new endpoint unprotected by
    construction, which is precisely how the /audits/federal leak survived.
    """
    schema = client.app.openapi()
    params = {
        "county_id": "001",
        "entity_id": str(COUNTY_ID),
        "country_id": str(COUNTRY_ID),
        "id": str(COUNTY_ID),
        "audit_id": "1",
        "period_id": "900",
        "document_id": "2392",
        "table_name": "audits",
        "record_id": "1",
        "job_id": "test-job-1",
        "slug": "nairobi-sentinel",
        "county_slug": "nairobi-sentinel",
        "sector": "health",
        "year": "2025",
        "fiscal_year": "FY2024/25",
        "question_id": "1",
        "category": "health",
        "term": "budget",
        "query": "budget",
    }
    urls, skipped = [], []
    for path, ops in schema.get("paths", {}).items():
        if "get" not in ops:
            continue
        if path.startswith(SKIP_PREFIXES):
            skipped.append((path, "auth-gated"))
            continue
        names = re.findall(r"\{(\w+)\}", path)
        missing = [n for n in names if n not in params]
        if missing:
            skipped.append((path, f"no fixture for {missing}"))
            continue
        url = path
        for n in names:
            url = url.replace("{" + n + "}", params[n])
        urls.append((path, url))
    return urls, skipped


def _sweep(client):
    """GET every public route; return {path: body} for those that answered."""
    urls, skipped = _public_get_routes(client)
    bodies, errored = {}, []
    for path, url in urls:
        try:
            r = client.get(url)
        except Exception as exc:  # a route that explodes cannot leak, but say so
            errored.append((path, f"{type(exc).__name__}: {exc}"))
            continue
        bodies[path] = r.text or ""
    return bodies, skipped, errored


# ── the sweep ──────────────────────────────────────────────────────────────
#
# One test, not five. Sweeping every public GET route costs ~60s, and running
# that once per assertion made the file take 5.5 minutes — a slow test gets
# excluded from the default run, and a regression test excluded from the
# default run protects nothing. Each property below keeps its own message.


def test_public_sweep_withholds_only_what_it_should(client, db_session, sentinels):
    from services.publication_gate import publishable_audit_criterion

    bodies, skipped, errored = _sweep(client)

    # 1. The sweep is meaningful. Guards against a vacuous pass: assertions
    #    about "appears nowhere" are trivially satisfied by hitting nothing.
    assert len(bodies) >= 20, (
        f"only {len(bodies)} routes exercised — too narrow to prove anything. "
        f"skipped={skipped}"
    )
    assert len(skipped) < len(bodies), f"more skipped than exercised: {skipped}"

    # 2. POSITIVE CONTROL, asserted before the negatives. A sourced figure must
    #    still reach the public; if it does not, every "appears nowhere" claim
    #    below is worthless. Do not weaken the negatives to make this pass.
    seen = [p for p, b in bodies.items() if _body_contains(b, LIT_AMOUNT)]
    assert seen, (
        "the publishable sentinel appeared on NO endpoint — the gate is "
        f"withholding sourced data, or the sweep is dead. "
        f"exercised={len(bodies)} skipped={len(skipped)} errored={errored}"
    )

    # 3. The withheld figure must not surface, in any rendering.
    leaks = [
        f"{p} leaked {hit!r}"
        for p, b in bodies.items()
        if (hit := _body_contains(b, DARK_AMOUNT))
    ]
    assert not leaks, "withheld figure served publicly:\n  " + "\n  ".join(leaks)

    # 4. Nor the finding text — it names an entity, which is the legal exposure.
    text_leaks = [p for p, b in bodies.items() if "dark sentinel finding" in b]
    assert not text_leaks, f"withheld finding text served publicly: {text_leaks}"

    # 5. Generalise past the sentinels to whatever is actually withheld.
    withheld = db_session.query(Audit).filter(~publishable_audit_criterion()).all()
    assert withheld, "no withheld rows in the fixture — this check would be vacuous"
    row_leaks = []
    for row in withheld:
        if row.amount is None or float(row.amount) == 0:
            continue  # collision-prone
        for path, body in bodies.items():
            if hit := _body_contains(body, Decimal(str(row.amount))):
                row_leaks.append(
                    f"audit id={row.id} amount={row.amount} on {path} ({hit!r})"
                )
    assert not row_leaks, "withheld rows served publicly:\n  " + "\n  ".join(row_leaks)


# ── the specific leak this task closes ─────────────────────────────────────


def test_federal_audits_total_excludes_withheld_rows(client, sentinels):
    """Assert the count, not just absence, so a rename still trips the test."""
    r = client.get("/api/v1/audits/federal")
    assert r.status_code == 200, r.text
    d = r.json()

    assert d["total_amount_in_findings"] == pytest.approx(float(LIT_AMOUNT)), (
        "total_amount_in_findings must sum only findings whose source document "
        f"resolves; got {d['total_amount_in_findings']}"
    )
    assert d["total_findings"] == 1, (
        f"expected only the sourced national finding, got {d['total_findings']}"
    )
    for f in d["findings"]:
        assert "dark sentinel" not in (f.get("finding") or "")


def test_federal_audits_reports_absent_total_as_null_not_zero(client, db_session):
    """With every federal finding withheld, the total is unknown — not 0.0."""
    from models import Audit

    # remove the sourced national finding, leaving only withheld ones
    db_session.query(Audit).delete()
    db_session.commit()

    d = client.get("/api/v1/audits/federal").json()
    assert d["total_amount_in_findings"] is None, (
        f"expected null, got {d['total_amount_in_findings']!r} — 0.0 reads as "
        "'the Auditor-General questioned nothing'"
    )
    assert d["total_amount_in_findings_reason"] is not None


def test_federal_audits_reports_what_it_withheld(client, sentinels):
    """A response that drops rows without saying so is the same defect."""
    d = client.get("/api/v1/audits/federal").json()
    assert d.get("withheld_findings") == 1, (
        f"expected withheld_findings=1, got {d.get('withheld_findings')!r}"
    )


def test_county_accountability_reports_absent_as_null_not_zero(client, sentinels):
    """`total_flagged_amount: 0.0` reads as 'nothing was flagged'. It is not.

    With only a withheld finding for this county, the honest answer is null
    plus a reason — never 0 (AUDIT_FINDINGS P1).
    """
    r = client.get(f"/api/v1/counties/{'001'}/accountability")
    assert r.status_code == 200, r.text
    d = r.json()
    total = d.get("total_flagged_amount")
    assert total != 0 and total != 0.0, (
        "absent flagged amount rendered as zero; expected null + reason"
    )
    assert d.get("withheld") is not None, "withheld count not reported"


# ── every row currently failing the predicate, not just the sentinels ──────


def test_no_row_failing_the_predicate_appears_anywhere(client, db_session, sentinels):
    """Generalises past the sentinels to whatever is actually withheld."""
    from services.publication_gate import publishable_audit_criterion

    withheld = (
        db_session.query(Audit).filter(~publishable_audit_criterion()).all()
    )
    assert withheld, "no withheld rows in the fixture — test would be vacuous"

    bodies, _, _ = _sweep(client)
    leaks = []
    for row in withheld:
        if row.amount is None or float(row.amount) == 0:
            continue  # collision-prone; skip
        for path, body in bodies.items():
            hit = _body_contains(body, Decimal(str(row.amount)))
            if hit:
                leaks.append(f"audit id={row.id} amount={row.amount} on {path} ({hit!r})")
    assert not leaks, "withheld rows served publicly:\n  " + "\n  ".join(leaks)
