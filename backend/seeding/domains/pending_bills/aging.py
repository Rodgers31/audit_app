"""Versioned CoB executive aging observations, separate from all-obligation stocks.

Only the reviewed edition is supported. Reissues require source review rather
than silently reusing a URL, page number or fiscal-year-derived age.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from models import Extraction
from services.pending_bills_aging import EXTRACTOR, absent_observation
from .parser import require_pending_amount

ARTIFACT_SHA256 = "919930622bc9fbc0c0b5cdcb566219e4f1432e7c9a3329dfd5bb23616cd33c20"
AS_AT = "2026-06-30"
TABLE = "Table 2.11"
BANDS = ("Under one year", "1-2 years", "2-3 years", "Over 3 years")
SCOPE = "county_executive"
MILLION = Decimal(1000000)


class AgingIngestion(dict):
    """In-process parse and acquisition envelope; serialized input is refused."""


def _county(label):
    from seeding.pdf_parsers import canonical_county_label

    return canonical_county_label(
        label.replace("*", "")
        .strip()
        .removesuffix(" County")
        .replace("Nairobi City", "Nairobi")
    )


def _amount(raw):
    if raw is None or (isinstance(raw, str) and raw.strip() in ("", "-", "–", "—")):
        return None
    value = require_pending_amount(raw, "aging cell")
    if value > Decimal("1e12"):
        raise ValueError("Aging cell exceeds the supported million-KES range")
    return str(value * MILLION)


def parse_aging_tables(tables, payables_entries):
    """Read complete six-column executive tables including every continuation.

    Dashes stay missing. Published totals are retained independently of known
    cells; rounding differences and publisher contradictions remain explicit.
    """
    from seeding.pdf_parsers import KENYAN_COUNTIES

    known = set(KENYAN_COUNTIES)
    if not isinstance(tables, list) or not isinstance(payables_entries, list):
        raise ValueError("Aging requires table pages and payables entries")
    payables = {e["county"]: e for e in payables_entries}
    if len(payables_entries) != 47 or set(payables) != known:
        raise ValueError("Aging requires the complete same-edition payables cohort")
    if {e.get("as_at") for e in payables_entries} != {AS_AT}:
        raise ValueError("Aging and payables dates differ")
    rows, total = {}, None
    for page, table in tables:
        if (
            type(page) is not int
            or page < 1
            or not isinstance(table, list)
            or len(table) < 3
        ):
            raise ValueError("Invalid aging table page")
        header = " ".join(str(c or "") for c in table[0]).lower()
        if "executive" not in header or "ageing" not in header:
            continue
        if "million" not in header:
            raise ValueError("Aging unit is not million KES")
        if [str(c or "").strip() for c in table[1]][1:5] != list(BANDS):
            raise ValueError("Unsupported aging bands")
        for cells in table[2:]:
            if not isinstance(cells, list) or len(cells) != 6:
                raise ValueError("Malformed aging row")
            label = cells[0]
            if not isinstance(label, str):
                raise ValueError("Missing aging county identity")
            name = _county(label)
            is_total = name.lower() == "total"
            if not is_total and name not in known:
                raise ValueError(f"Unknown aging county: {label}")
            if name in rows or (is_total and total is not None):
                raise ValueError(f"Duplicated aging county/total: {name}")
            values = [_amount(c) for c in cells[1:]]
            notes = []
            if name == "Nandi":
                # PDF p.54 explicitly says no aging analysis was supplied.
                # Preserve the printed zeros as raw evidence, never a measured
                # zero balance overriding the publisher's qualification.
                values = [None] * 5
                notes.append(
                    {
                        "code": "publisher_says_aging_not_provided",
                        "table": TABLE,
                        "page": 54,
                        "county": "Nandi",
                    }
                )
            if "*" in label:
                notes.append({"code": "cob_marked_inconsistent", "table": TABLE})
            if any(v is None for v in values):
                notes.append({"code": "missing_source_cells", "table": TABLE})
            elif abs(
                sum(Decimal(v) for v in values[:4]) - Decimal(values[4])
            ) > Decimal(50000):
                notes.append(
                    {"code": "bands_differ_from_printed_total", "table": TABLE}
                )
            if not is_total:
                executive = _amount(payables[name].get("executive_millions"))
                if (
                    executive is not None
                    and values[4] is not None
                    and abs(Decimal(executive) - Decimal(values[4])) > Decimal(50000)
                ):
                    notes.append(
                        {
                            "code": "payables_executive_total_differs",
                            "table": TABLE,
                            "comparison_table": payables[name]["table"],
                            "comparison_page": payables[name]["page"],
                            "comparison_amount": executive,
                        }
                    )
            row = dict(
                county=name,
                page=page,
                raw_cells=deepcopy(cells[1:]),
                amounts=values,
                reader_notes=notes,
            )
            if is_total:
                total = row
            else:
                rows[name] = row
    if set(rows) != known or total is None:
        raise ValueError("Incomplete executive aging table/continuation")
    if any(v is None for v in total["amounts"]):
        raise ValueError("Executive aging printed summary is incomplete")
    payables_sum = sum(
        (
            Decimal(_amount(e["executive_millions"]))
            for e in payables_entries
            if e.get("executive_millions") is not None
        ),
        Decimal(0),
    )
    if abs(payables_sum - Decimal(total["amounts"][4])) > Decimal(500000):
        total["reader_notes"].append(
            {
                "code": "known_payables_executive_sum_differs",
                "table": TABLE,
                "comparison_table": "Table 2.10",
                "comparison_amount": str(payables_sum),
                "aging_reported_total": total["amounts"][4],
            }
        )
    # Known cells can be compared, but missing cells cannot be added as zero.
    reconciliation = []
    for i, band in enumerate((*BANDS, "Total")):
        present = [
            Decimal(r["amounts"][i])
            for r in rows.values()
            if r["amounts"][i] is not None
        ]
        printed = Decimal(total["amounts"][i])
        reconciliation.append(
            dict(
                column=band,
                known_cells_sum=str(sum(present, Decimal(0))),
                printed_amount=str(printed),
                reported_count=len(present),
                status="not_reconciled_missing_cells"
                if len(present) != 47
                else "matched_with_rounding"
                if abs(sum(present) - printed) <= Decimal(500000)
                else "conflicting",
            )
        )
    return dict(
        version=1,
        scope=SCOPE,
        as_at=AS_AT,
        fiscal_year="FY2025/26",
        table=TABLE,
        unit="KES",
        raw_unit="KES million",
        bands=list(BANDS),
        rows=[rows[n] for n in KENYAN_COUNTIES],
        summary=total,
        reconciliation=reconciliation,
        artifact_sha256=ARTIFACT_SHA256,
    )


class ExecutiveAgingParser:
    def __init__(self, path, payables_entries):
        self.path, self.payables_entries = Path(path), payables_entries

    def parse(self):
        import pdfplumber

        with self.path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != ARTIFACT_SHA256:
            raise ValueError(
                "Unreviewed aging artifact/reissue; source qualification required"
            )
        with pdfplumber.open(self.path) as pdf:
            tables = []
            for page_no in (53, 54):
                page = pdf.pages[page_no - 1]
                try:
                    text = page.extract_text() or ""
                    if page_no == 53 and (
                        "Table 2.11: Trade Payables Ageing Analysis for County Executives as of 30 June 2026"
                        not in text
                    ):
                        raise ValueError("Aging caption missing from reviewed edition")
                    if (
                        page_no == 54
                        and "Nandi County Government did not provide an ageing analysis of payables as of 30 June 2026"
                        not in text
                    ):
                        raise ValueError("Aging missing-data qualification absent")
                    tables.extend((page_no, t) for t in page.extract_tables())
                finally:
                    page.flush_cache()
        # The existing parse attestation binds JSON-safe lists to input bytes.
        return [parse_aging_tables(tables, self.payables_entries)]


def _identity(row, column):
    return dict(
        measure=f"pending_bills_aging_{column}",
        geography=row["county"],
        entity_id=None,
        period=AS_AT,
        unit="KES",
        basis="actual",
        dimensions={"population": SCOPE, "band": column},
    )


def prepare_aging(parsed_records, receipt):
    from seeding.pdf_evidence import cell_evidence, seal_pdf_observations
    from seeding.parse_cache import fresh_parse_matches

    if (
        receipt.get("digest") != ARTIFACT_SHA256
        or not fresh_parse_matches(parsed_records, ARTIFACT_SHA256)
        or len(parsed_records) != 1
    ):
        raise ValueError("Aging requires a fresh parse of the reviewed artifact")
    cohort = parsed_records[0]
    validate_cohort(cohort)
    result = AgingIngestion(deepcopy(cohort))
    evidence = []
    for row in [*result["rows"], result["summary"]]:
        row["source_evidence"] = []
        for i, column in enumerate((*BANDS, "Total")):
            if row["amounts"][i] is None:
                continue
            cell = cell_evidence(
                receipt=receipt,
                identity=_identity(row, column),
                raw_value=str(row["raw_cells"][i]).replace(",", ""),
                value=row["amounts"][i],
                raw_unit="KES million",
                factor="1000000",
                locator={
                    "page": row["page"],
                    "table": TABLE,
                    "cell": f"{row['county']} / {column}",
                },
            )
            row["source_evidence"].append(cell)
            evidence.append(cell)
    seal_pdf_observations(evidence)
    result._snapshot = _envelope_fingerprint(result)
    return result


def _envelope_fingerprint(cohort):
    return hashlib.sha256(json.dumps(dict(cohort), sort_keys=True).encode()).hexdigest()


def require_intact_aging(cohort):
    if not isinstance(cohort, AgingIngestion) or getattr(
        cohort, "_snapshot", None
    ) != _envelope_fingerprint(cohort):
        raise ValueError(
            "Aging requires an intact in-process source acquisition envelope"
        )
    validate_cohort(cohort)


def cohort_fingerprint(cohort):
    normalized = deepcopy(dict(cohort))
    for row in [*normalized["rows"], normalized["summary"]]:
        row.pop("source_evidence", None)
    return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()


def persist_aging(session, source, cohort, *, publication_batch, records):
    from seeding.pdf_evidence import bind_pdf_evidence

    require_intact_aging(cohort)
    if {r.as_at for r in records} != {AS_AT} or any(
        r.entity_type != "county" for r in records
    ):
        raise ValueError("Aging and pending-bills populations/dates differ")
    digests = {
        e.get("_response_receipt", {}).get("digest")
        for r in records
        for e in r.source_evidence
    }
    if digests != {ARTIFACT_SHA256} or any(not r.source_evidence for r in records):
        raise ValueError("Aging and payables must bind the same PDF artifact")
    bound = deepcopy(dict(cohort))
    for row in [*bound["rows"], bound["summary"]]:
        identity = _identity(row, "Total")
        identity.pop("measure")
        # Each band has a distinct observation dimension.
        evidence = []
        for item in row["source_evidence"]:
            identity["dimensions"] = item["identity"]["dimensions"]
            evidence.extend(
                bind_pdf_evidence(
                    session,
                    source,
                    [item],
                    identity=identity,
                    values={item["identity"]["measure"]: item["value"]},
                )
            )
        row["source_evidence"] = evidence
    fingerprint = cohort_fingerprint(bound)
    ref = dict(
        artifact_sha256=ARTIFACT_SHA256,
        as_at=AS_AT,
        publication_batch=publication_batch,
        fingerprint=fingerprint,
        source_url=source.url,
    )
    # Validate this incoming acquisition before choosing a deduplicated prior
    # observation. A valid older cohort cannot license a corrupted replay.
    candidate = Extraction(
        source_document_id=source.id,
        extractor=EXTRACTOR,
        page_number=53,
        extracted_json=bound,
    )
    check = public_observation(session, source, candidate, ref)
    if check["status"] == "unavailable":
        raise ValueError(f"Aging source evidence refused: {check['absent_reason']}")
    prior = (
        session.query(Extraction)
        .filter(
            Extraction.source_document_id == source.id,
            Extraction.extractor == EXTRACTOR,
        )
        .all()
    )
    existing = next(
        (e for e in prior if cohort_fingerprint(e.extracted_json) == fingerprint), None
    )
    if existing is None:
        existing = candidate
        session.add(existing)
        session.flush()
    ref["extraction_id"] = existing.id
    return ref


def validate_cohort(cohort):
    from seeding.pdf_parsers import KENYAN_COUNTIES

    if (
        not isinstance(cohort, dict)
        or cohort.get("version") != 1
        or type(cohort.get("version")) is not int
    ):
        raise ValueError("Unsupported aging schema")
    if any(
        cohort.get(k) != v
        for k, v in dict(
            scope=SCOPE,
            as_at=AS_AT,
            table=TABLE,
            unit="KES",
            raw_unit="KES million",
            bands=list(BANDS),
            artifact_sha256=ARTIFACT_SHA256,
        ).items()
    ):
        raise ValueError("Unsupported aging source/scope/bands")
    rows = cohort.get("rows")
    if (
        not isinstance(rows, list)
        or len(rows) != 47
        or {r.get("county") for r in rows} != set(KENYAN_COUNTIES)
    ):
        raise ValueError("Incomplete/duplicated aging cohort")
    for row in [*rows, cohort.get("summary")]:
        if (
            not isinstance(row, dict)
            or type(row.get("page")) is not int
            or row["page"] not in (53, 54, 55)
        ):
            raise ValueError("Invalid aging locator")
        if not isinstance(row.get("raw_cells"), list) or len(row["raw_cells"]) != 5:
            raise ValueError("Invalid aging cells")
        normalized = (
            [None] * 5
            if row["county"] == "Nandi"
            else [_amount(c) for c in row["raw_cells"]]
        )
        if normalized != row.get("amounts"):
            raise ValueError("Aging raw and normalized cells disagree")


def public_observation(db, source, extraction, ref, *, county=None):
    from services.figure_qualification import (
        ObservationIdentity,
        evaluate_qualification,
    )

    cohort = extraction.extracted_json
    try:
        validate_cohort(cohort)
        if (
            cohort_fingerprint(cohort) != ref.get("fingerprint")
            or ref.get("artifact_sha256") != ARTIFACT_SHA256
        ):
            raise ValueError("Changed aging extraction")
        row = (
            next((r for r in cohort["rows"] if r["county"] == _county(county)), None)
            if county
            else cohort["summary"]
        )
        if row is None:
            return absent_observation(SCOPE, "county_not_in_aging_cohort")
        all_rows = [*cohort["rows"], cohort["summary"]]
        ids = {
            e.get("receipt", {}).get("extraction_id")
            for r in all_rows
            for e in r.get("source_evidence", [])
        }
        receipts = {
            e.id: e.extracted_json.get("response_receipt")
            for e in db.query(Extraction)
            .filter(
                Extraction.id.in_(list(ids)), Extraction.source_document_id == source.id
            )
            .all()
        }
        qualifications = []
        for checked_row in all_rows:
            evidence = checked_row.get("source_evidence", [])
            if len(evidence) != sum(v is not None for v in checked_row["amounts"]):
                raise ValueError("Missing/extra aging evidence")
            for i, column in enumerate((*BANDS, "Total")):
                value = checked_row["amounts"][i]
                if value is None:
                    continue
                matches = [
                    e
                    for e in evidence
                    if e.get("identity") == _identity(checked_row, column)
                ]
                if len(matches) != 1:
                    raise ValueError("Missing/ambiguous aging cell evidence")
                cell = matches[0]
                q = evaluate_qualification(
                    ObservationIdentity(**_identity(checked_row, column)),
                    value,
                    source=source,
                    evidence=cell,
                    receipt=receipts.get(cell["receipt"]["extraction_id"]),
                )
                if q.status != "verified" or q.digest != ARTIFACT_SHA256:
                    raise ValueError(f"Aging cell evidence: {q.reason}")
                if checked_row is row:
                    qualifications.append(q.model_dump())
    except (ValueError, TypeError, KeyError, AttributeError):
        return absent_observation(SCOPE, "invalid_or_unqualified_aging_evidence")
    missing = [r["county"] for r in cohort["rows"] if r["amounts"][4] is None]
    qualified = [r["county"] for r in cohort["rows"] if r["reader_notes"]]
    notes = deepcopy(row["reader_notes"])
    if not county:
        notes.append({"code": "reported_executive_population_only", "table": TABLE})
    buckets = [
        dict(
            bucket=band,
            amount=float(row["amounts"][i]) if row["amounts"][i] is not None else None,
            raw_value=row["raw_cells"][i],
            absent_reason="source_cell_not_reported"
            if row["amounts"][i] is None
            else None,
        )
        for i, band in enumerate(BANDS)
    ]
    return dict(
        version=1,
        scope=SCOPE,
        status="qualified",
        absent_reason=None,
        as_at=AS_AT,
        currency="KES",
        unit="KES",
        raw_unit="KES million",
        source_document_id=source.id,
        extraction_id=extraction.id,
        artifact_sha256=ARTIFACT_SHA256,
        source_url=source.url,
        source_title=source.title,
        publisher=source.publisher,
        table=TABLE,
        page=row["page"],
        county=county,
        buckets=buckets,
        reported_total=float(row["amounts"][4])
        if row["amounts"][4] is not None
        else None,
        complete_total=None,
        complete_total_absent_reason="incomplete_or_qualified_source_population",
        coverage=dict(
            reported_counties=47 - len(missing),
            expected_counties=47,
            missing_counties=missing,
            qualified_counties=qualified,
            complete=False,
        ),
        reader_notes=notes,
        reconciliation=cohort["reconciliation"],
        qualifications=qualifications,
        chart_supported=all(b["amount"] is not None for b in buckets)
        and not any(n["code"] == "bands_differ_from_printed_total" for n in notes),
    )
