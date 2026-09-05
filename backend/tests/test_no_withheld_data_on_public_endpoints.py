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

import json
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
    # Required query parameters. Without these the route answers 422 and its
    # empty body looks exactly like a route that ran and leaked nothing — the
    # money-flow endpoints summed Audit.amount ungated for a whole task while
    # this sweep reported them clean.
    query_defaults = {
        "year": "FY2024/25",
        "fiscal_year": "FY2024/25",
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
        required_q = [
            q["name"]
            for q in ops["get"].get("parameters", [])
            if q.get("in") == "query" and q.get("required")
        ]
        unfillable = [q for q in required_q if q not in query_defaults]
        if unfillable:
            skipped.append((path, f"required query param {unfillable}"))
            continue
        if required_q:
            url += "?" + "&".join(f"{q}={query_defaults[q]}" for q in required_q)
        urls.append((path, url))
    return urls, skipped


def _sweep(client):
    """GET every public route.

    Returns ``(bodies, skipped, errored)``. ``errored`` holds routes that
    raised or answered non-2xx — those bodies carry no data, so finding no
    sentinel in them proves nothing. They are reported, never counted as clean.
    """
    urls, skipped = _public_get_routes(client)
    bodies, errored = {}, []
    for path, url in urls:
        try:
            r = client.get(url)
        except Exception as exc:  # a route that explodes cannot leak, but say so
            errored.append((path, f"{type(exc).__name__}: {exc}"))
            continue
        if not (200 <= r.status_code < 300):
            errored.append((path, f"HTTP {r.status_code}"))
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
        f"only {len(bodies)} routes answered 2xx — too narrow to prove "
        f"anything. skipped={skipped} errored={errored}"
    )
    assert len(skipped) < len(bodies), f"more skipped than exercised: {skipped}"
    # A route answering 4xx/5xx contributes no body, so "no sentinel found"
    # in it is not evidence. Keep that population small and visible.
    assert len(errored) <= len(bodies) // 2, (
        f"{len(errored)} of {len(bodies) + len(errored)} routes did not return "
        f"2xx, so most of the sweep proves nothing: {errored}"
    )
    # The money-flow endpoints sum Audit.amount; they must be genuinely covered.
    money_flow = [p for p in bodies if "money-flow" in p]
    assert len(money_flow) >= 3, (
        f"money-flow routes not covered by the sweep (got {money_flow}); "
        f"errored={[e for e in errored if 'money' in e[0]]}"
    )

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

    # 6. Same fabricated dataset, second storage location: the hardcoded OAG
    #    JSON files, whose only citation is a bare domain.
    file_leaks = []
    for amount in sorted(_static_file_amounts()):
        for path, body in bodies.items():
            if hit := _body_contains(body, amount):
                file_leaks.append(f"{path} served {hit!r} (from a hardcoded OAG file)")
    assert not file_leaks, (
        "hardcoded file figures served publicly:\n  "
        + "\n  ".join(sorted(set(file_leaks)))
    )

    # 7. Removing the numeric field is not enough — the prose quotes it.
    #    "Unexplained Consolidated Fund balance differences of KES 156.8 billion"
    prose = re.compile(r"KES\s*[\d,.]+\s*(?:billion|million|trillion|B|M|T)\b", re.I)
    prose_leaks = []
    for path, body in bodies.items():
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            continue
        for field in ("basis_for_qualification", "emphasis_of_matter"):
            for item in _iter_strings(payload, field):
                if prose.search(item):
                    prose_leaks.append(f"{path} {field}: {item[:90]!r}")
    assert not prose_leaks, (
        "prose quoting an unpublishable KES figure:\n  " + "\n  ".join(prose_leaks)
    )


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


# ── Stage 0.2: the same fabricated dataset, stored in a second place ───────
#
# Gating the database closed one door. The identical figures also live in
# backend/data/reference/oag_national_audit_data.json (24 amounts, sum 3,313,000,000,000 — the
# same sum as the quarantined rows, 22 of 24 amounts byte-identical), whose
# only citation is the bare domain "https://www.oagkenya.go.ke". These parse
# the files rather than hardcoding numbers, so re-seeding cannot stale them.

# See the note in test_bootstrap_is_observable: bootstrap owns this path.
from bootstrap import DATA_DIR as APIS_DIR


def _kes(value):
    """Parse 'KES 981.3B' / '1.2T' / '500M' into a float, else None."""
    if not value:
        return None
    s = str(value).upper().replace("KES", "").strip()
    mult = 1.0
    for suffix, m in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if s.endswith(suffix):
            mult, s = m, s[:-1]
            break
    try:
        return float(s.replace(",", "").strip()) * mult
    except (ValueError, TypeError):
        return None


def _static_file_amounts():
    """Every KES figure in either hardcoded OAG file, parsed from the files."""
    amounts: set[Decimal] = set()
    for name in ("oag_national_audit_data.json", "oag_audit_data.json"):
        path = APIS_DIR / name
        if not path.exists():
            continue
        blob = json.loads(path.read_text())

        def walk(node):
            if isinstance(node, dict):
                for k, v in node.items():
                    if isinstance(v, str) and (
                        "amount" in k.lower() or "questioned" in k.lower()
                    ):
                        if (n := _kes(v)) and n >= 1_000_000:
                            amounts.add(Decimal(str(n)))
                    else:
                        walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(blob)
    return amounts


def test_the_static_files_still_hold_the_fabricated_figures(client):
    """Anti-vacuity for the two tests below: if the files were emptied or
    deleted, those tests would pass by finding nothing to look for."""
    amounts = _static_file_amounts()
    assert len(amounts) >= 20, (
        f"expected the hardcoded OAG files to still hold their figures "
        f"(retain, never delete); found {len(amounts)}"
    )


def _iter_strings(node, field):
    """Yield every string under any occurrence of ``field`` in a payload."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == field:
                if isinstance(v, str):
                    yield v
                elif isinstance(v, list):
                    yield from (x for x in v if isinstance(x, str))
            else:
                yield from _iter_strings(v, field)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_strings(v, field)


def test_federal_severity_histogram_agrees_with_its_own_finding_count(
    client, sentinels
):
    """A histogram describing rows the same response says are withheld."""
    d = client.get("/api/v1/audits/federal").json()
    by_sev = d.get("by_severity") or {}
    if not by_sev:
        return  # withholding it entirely is an acceptable answer
    assert sum(by_sev.values()) == d["total_findings"], (
        f"by_severity sums to {sum(by_sev.values())} but total_findings is "
        f"{d['total_findings']} — the same response contradicts itself"
    )


def test_a_finding_of_broken_glyphs_is_not_published(client, db_session, sentinels):
    """Text integrity (IMPLEMENTATION_PROMPT A.4).

    Audit 902's finding_text is 89.6% ``(cid:NN)`` tokens ending in the report's
    VISION statement — the PDF's cover page, not a finding.
    """
    from models import Audit

    entity_id = NATIONAL_ID
    db_session.add(
        Audit(
            entity_id=entity_id,
            period_id=900,
            finding_text="(cid:31)(cid:30)(cid:29)(cid:28)(cid:27)(cid:26) VISION Making a diff",
            severity=Severity.CRITICAL,
            source_document_id=2392,  # a document that DOES resolve
            amount=None,
            audit_year=2025,
            provenance=[{"amount_involved": "", "status": "pending"}],
        )
    )
    db_session.commit()

    bodies, _, _ = _sweep(client)
    leaks = [p for p, b in bodies.items() if "(cid:" in b]
    assert not leaks, f"glyph-code finding text served publicly: {leaks}"


@pytest.fixture()
def unaudited_county(db_session, seed_country):
    """A county with no audit rows at all — the state of 46 of 47 in production."""
    county = Entity(
        id=902,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Wajir County",
        slug="wajir-unaudited",
        meta={"county_code": "008"},
    )
    db_session.add(county)
    db_session.commit()
    return county


def test_absence_is_never_graded(client, sentinels, unaudited_county):
    """A county with no audit evidence must not be scored — least of all an A.

    46 of 47 counties have zero audit rows (only Homa Bay has one). The
    scorecard starts at 100 and subtracts penalties, so "no data" produces a
    near-perfect grade that reads as a clean bill of health.
    """
    d = client.get("/api/v1/counties/008/accountability").json()
    basis = d.get("evidence_basis")
    assert basis in ("no_findings_recorded", "no_publishable_findings"), (
        f"fixture did not reach the no-evidence path (basis={basis!r}); this "
        "test would prove nothing"
    )
    assert d.get("accountability_grade") is None, (
        f"evidence_basis={basis!r} but graded {d['accountability_grade']!r}"
    )
    assert d.get("accountability_score") is None, (
        f"evidence_basis={basis!r} but scored {d['accountability_score']!r}"
    )
    assert d.get("accountability_reason"), "no reason given for the absent grade"


def test_a_sourced_file_figure_would_still_publish(client, sentinels, tmp_path):
    """POSITIVE CONTROL for the file path.

    The file gate must reject *unsourced* files, not all files. Without this,
    deleting the feature entirely would satisfy every negative assertion above.
    """
    from services.publication_gate import file_source_provenance_failure

    assert file_source_provenance_failure({}) is not None
    assert (
        file_source_provenance_failure({"source": "https://www.oagkenya.go.ke"})
        is not None
    ), "a bare domain is a homepage, not a source document"
    assert (
        file_source_provenance_failure(
            {
                "source_url": (
                    "https://www.oagkenya.go.ke/wp-content/uploads/2026/05/report.pdf"
                ),
                "page_ref": "p. 14",
            }
        )
        is None
    ), "a file citing a real document and a page must still publish"


# ── aggregates: a sentinel absorbed into a sum is invisible to exact match ──
#
# The sweep above matches a withheld figure's exact rendering. That cannot see
# a withheld value added into a total: un-gating the money-flow endpoints makes
# their "Flagged" stage 123456789.07 + 987654321.01, which matches neither
# sentinel. Endpoints that aggregate need their arithmetic asserted, not their
# text searched.


def _flagged_stage(payload):
    """The 'Flagged' stage amount from a money-flow payload."""
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    for stage in (payload or {}).get("stages", []):
        if stage.get("stage") == "Flagged":
            return stage.get("amount")
    return None


@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/counties/001/money-flow?year=FY2024/25",
        "/api/v1/audit/money-flow/national?year=FY2024/25",
        "/api/v1/money-flow/all-counties?year=FY2024/25",
    ],
)
def test_money_flow_flagged_total_sums_only_publishable_findings(
    client, sentinels, url
):
    r = client.get(url)
    assert r.status_code == 200, r.text
    flagged = _flagged_stage(r.json())
    assert flagged == pytest.approx(float(LIT_AMOUNT)), (
        f"{url} flagged {flagged!r}; expected only the publishable sentinel "
        f"({float(LIT_AMOUNT)}). A total including the withheld "
        f"{float(DARK_AMOUNT)} would be {float(LIT_AMOUNT) + float(DARK_AMOUNT)}."
    )
