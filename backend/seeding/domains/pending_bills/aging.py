"""Versioned CoB population-specific aging observations, separate from all-obligation stocks.

Only the reviewed edition is supported. Reissues require source review rather
than silently reusing a URL, page number or fiscal-year-derived age.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import logging
import re
from pathlib import Path

from models import Extraction
from services.pending_bills_aging import EXTRACTOR, ASSEMBLY_EXTRACTOR, absent_observation
from .parser import require_pending_amount

ARTIFACT_SHA256 = "919930622bc9fbc0c0b5cdcb566219e4f1432e7c9a3329dfd5bb23616cd33c20"
# Legacy SourceDocument checksum for this same reviewed byte edition.
ARTIFACT_MD5 = "dfafc8c1d53ea3258ea485ddec0b3fd6"
AS_AT = "2026-06-30"
FISCAL_YEAR = "FY2025/26"
TABLE = "Table 2.11"
BANDS = ("Under one year", "1-2 years", "2-3 years", "Over 3 years")
SCOPE = "county_executive"
MILLION = Decimal(1000000)
ASSEMBLY_SCOPE = "county_assembly"
logger = logging.getLogger("seeding.pending_bills.aging")


def scope_contract(scope):
    if scope == SCOPE:
        return dict(version=1, table=TABLE, pages=(53, 54), extractor=EXTRACTOR,
                    metadata_key="pending_bills_aging_v1", population="executive")
    if scope == ASSEMBLY_SCOPE:
        return dict(version=2, table="Table 2.12", pages=(54, 55), extractor=ASSEMBLY_EXTRACTOR,
                    metadata_key="pending_bills_assembly_aging_v2", population="assembly")
    raise ValueError("Unsupported aging scope")


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


def parse_aging_tables(tables, payables_entries, *, scope=SCOPE):
    """Read one population’s six-column table including every continuation.

    Dashes stay missing. Published totals are retained independently of known
    cells; rounding differences and publisher contradictions remain explicit.
    """
    from seeding.pdf_parsers import KENYAN_COUNTIES

    contract = scope_contract(scope)
    table_name = contract["table"]
    population = contract["population"]
    stock_field = f"{population}_millions"
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
        if scope == SCOPE:
            if "executive" not in header or "ageing" not in header:
                continue
        elif str(table[0][1] or "").strip() != "County Ass )":
            continue
        if page not in contract["pages"]:
            raise ValueError("Invalid aging population page")
        header = header.replace("mil-\nlions", "millions")
        units = re.findall(r"\b([a-z]+)\.?\s*millions?\b", header)
        if not units or any(unit not in {"kes", "ksh", "kshs"} for unit in units):
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
            if name == "Nandi" and scope == SCOPE:
                # PDF p.54 explicitly says no aging analysis was supplied.
                # Preserve the printed zeros as raw evidence, never a measured
                # zero balance overriding the publisher's qualification.
                values = [None] * 5
                notes.append(
                    {
                        "code": "publisher_says_aging_not_provided",
                        "table": table_name,
                        "page": 54,
                        "county": "Nandi",
                    }
                )
            if "*" in label:
                notes.append({"code": "cob_marked_inconsistent", "table": table_name})
            if any(v is None for v in values):
                notes.append({"code": "missing_source_cells", "table": table_name})
            elif abs(
                sum(Decimal(v) for v in values[:4]) - Decimal(values[4])
            ) > Decimal(50000):
                notes.append(
                    {"code": "bands_differ_from_printed_total", "table": table_name}
                )
            if not is_total:
                stock_amount = _amount(payables[name].get(stock_field))
                if (
                    stock_amount is not None
                    and values[4] is not None
                    and abs(Decimal(stock_amount) - Decimal(values[4])) > Decimal(50000)
                ):
                    notes.append(
                        {
                            "code": f"payables_{population}_total_differs",
                            "table": table_name,
                            "comparison_table": payables[name]["table"],
                            "comparison_page": payables[name]["page"],
                            "comparison_amount": stock_amount,
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
        raise ValueError(f"Incomplete {population} aging table/continuation")
    if any(v is None for v in total["amounts"]):
        raise ValueError(f"{population.capitalize()} aging printed summary is incomplete")
    payables_sum = sum(
        (
            Decimal(_amount(e[stock_field]))
            for e in payables_entries
            if e.get(stock_field) is not None
        ),
        Decimal(0),
    )
    if abs(payables_sum - Decimal(total["amounts"][4])) > Decimal(500000):
        total["reader_notes"].append(
            {
                "code": f"known_payables_{population}_sum_differs",
                "table": table_name,
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
        version=contract["version"],
        scope=scope,
        as_at=AS_AT,
        fiscal_year=FISCAL_YEAR,
        table=table_name,
        unit="KES",
        raw_unit="KES million",
        bands=list(BANDS),
        rows=[rows[n] for n in KENYAN_COUNTIES],
        summary=total,
        reconciliation=reconciliation,
        artifact_sha256=ARTIFACT_SHA256,
    )


class ExecutiveAgingParser:
    scope = SCOPE

    def __init__(self, path, payables_entries):
        self.path, self.payables_entries = Path(path), payables_entries

    def parse(self):
        return _parse_pdf_scopes(self.path, self.payables_entries, [self.scope])


class AssemblyAgingParser(ExecutiveAgingParser):
    scope = ASSEMBLY_SCOPE


def _parse_pdf_scopes(path, payables_entries, scopes):
    """Open the retained edition once and inspect only the required pages."""
    import pdfplumber

    with Path(path).open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != ARTIFACT_SHA256:
        raise ValueError("Unreviewed aging artifact/reissue; source qualification required")
    tables = []
    pages = sorted({p for scope in scopes for p in scope_contract(scope)["pages"]})
    with pdfplumber.open(path) as pdf:
        for page_no in pages:
            page = pdf.pages[page_no - 1]
            try:
                text = page.extract_text() or ""
                required = []
                if SCOPE in scopes:
                    if page_no == 53:
                        required.append("Table 2.11: Trade Payables Ageing Analysis for County Executives as of 30 June 2026")
                    if page_no == 54:
                        required.append("Nandi County Government did not provide an ageing analysis of payables as of 30 June 2026")
                if ASSEMBLY_SCOPE in scopes:
                    if page_no == 54:
                        required.append("Table 2.12: Trade Payables Ageing Analysis for County Assemblies as of 30 June 2026")
                    if page_no == 55:
                        required.extend(["ageing analysis in Table 2.12", "Counties with an asterisk.", "Source: County Assemblies"])
                if any(caption not in text for caption in required):
                    raise ValueError("Aging caption or publisher qualification missing from reviewed edition")
                tables.extend((page_no, t) for t in page.extract_tables())
            finally:
                page.flush_cache()
    return [parse_aging_tables(tables, payables_entries, scope=scope) for scope in scopes]


def _identity(row, column, scope=SCOPE):
    return dict(
        measure=f"pending_bills_aging_{column}",
        geography=row["county"],
        entity_id=None,
        period=AS_AT,
        unit="KES",
        basis="actual",
        dimensions={"population": scope, "band": column},
    )


def prepare_aging(parsed_records, receipt, *, scope=None):
    from seeding.pdf_evidence import cell_evidence, seal_pdf_observations
    from seeding.parse_cache import fresh_parse_matches

    if (
        receipt.get("digest") != ARTIFACT_SHA256
        or not fresh_parse_matches(parsed_records, ARTIFACT_SHA256)
        or not parsed_records
        or (scope is None and len(parsed_records) != 1)
    ):
        raise ValueError("Aging requires a fresh parse of the reviewed artifact")
    if scope is None:
        cohort = parsed_records[0]
    else:
        matches = [c for c in parsed_records if c.get("scope") == scope]
        if len(matches) != 1:
            raise ValueError("Missing/duplicated parsed aging population")
        cohort = matches[0]
    for candidate in parsed_records:
        validate_cohort(candidate)
    result = AgingIngestion(deepcopy(cohort))
    scope = result["scope"]
    evidence = []
    for row in [*result["rows"], result["summary"]]:
        row["source_evidence"] = []
        for i, column in enumerate((*BANDS, "Total")):
            if row["amounts"][i] is None:
                continue
            cell = cell_evidence(
                receipt=receipt,
                identity=_identity(row, column, scope),
                raw_value=str(row["raw_cells"][i]).replace(",", ""),
                value=row["amounts"][i],
                raw_unit="KES million",
                factor="1000000",
                locator={
                    "page": row["page"],
                    "table": result["table"],
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


def require_stock_binding(cohort, records):
    """Validate the same edition for writes, direct persistence and dry previews."""
    require_intact_aging(cohort)
    if {r.as_at for r in records} != {AS_AT} or any(
        r.entity_type != "county" for r in records
    ):
        raise ValueError("Aging and pending-bills populations/dates differ")
    if any(re.fullmatch(r"FY\s*2025/26", r.fiscal_year) is None for r in records):
        raise ValueError("Aging and pending-bills fiscal years differ")
    digests = {
        e.get("_response_receipt", {}).get("digest")
        for r in records
        for e in r.source_evidence
    }
    if digests != {ARTIFACT_SHA256} or any(not r.source_evidence for r in records):
        raise ValueError("Aging and payables must bind the same PDF artifact")


def persist_aging(session, source, cohort, *, publication_batch, records):
    from seeding.pdf_evidence import bind_pdf_evidence

    require_stock_binding(cohort, records)
    bound = deepcopy(dict(cohort))
    scope = bound["scope"]
    contract = scope_contract(scope)
    for row in [*bound["rows"], bound["summary"]]:
        identity = _identity(row, "Total", scope)
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
        extractor=contract["extractor"],
        page_number=contract["pages"][0],
        extracted_json=bound,
    )
    check = public_observation(session, source, candidate, ref, scope=scope)
    if check["status"] == "unavailable":
        raise ValueError(f"Aging source evidence refused: {check['absent_reason']}")
    prior = (
        session.query(Extraction)
        .filter(
            Extraction.source_document_id == source.id,
            Extraction.extractor == contract["extractor"],
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
    # A successful flush can still have been transformed by the database.
    # Read the durable extraction and receipts back before returning success;
    # a failure propagates to the county writer's savepoint.
    session.refresh(existing)
    stored = public_observation(session, source, existing, ref, scope=scope)
    if stored["status"] == "unavailable":
        raise ValueError("Aging persisted evidence failed readback qualification")
    return ref


def retain_aging_pointers(session, source, previous, *, publication_batch,
                          county_table, stock_observations, context, was_current):
    """Keep observations only across a qualified reread of the identical stock.

    Flags select new acquisition, not deletion of already qualified evidence.
    A correction, changed absence statement, edition or unqualified stock write
    invalidates selection. Historical extractions are never rewritten/revived.
    """
    from services.figure_qualification import ObservationIdentity, evaluate_qualification
    from models import IngestionJob
    from seeding.retained_report_receipts import KEY, aware, validate_retained_pdf
    from datetime import datetime, timezone

    refs = {scope: previous.get(scope_contract(scope)["metadata_key"])
            for scope in (SCOPE, ASSEMBLY_SCOPE)}
    if not any(refs.values()):
        return {}
    if (was_current is not True
            or previous.get("pending_bills_publication_batch") != publication_batch
            or previous.get("county_payables") != county_table or not stock_observations):
        logger.info("Aging pointers cleared: county stock edition or coverage replaced")
        return {}
    # Qualify the newly persisted stock evidence, not its supplied digest or
    # an earlier cohort. Fetch receipts once for the entire stock publication.
    ids = {e.get("receipt", {}).get("extraction_id")
           for _, _, evidence in stock_observations for e in evidence}
    receipts = {e.id: e.extracted_json.get("response_receipt")
                for e in session.query(Extraction).populate_existing().filter(
                    Extraction.id.in_([i for i in ids if type(i) is int]),
                    Extraction.source_document_id == source.id).all()}
    try:
        for receipt in receipts.values():
            if isinstance(receipt, dict) and KEY in receipt:
                if context is None or type(context.job_id) is not int:
                    raise ValueError("Current retained-source job required")
                job = session.get(IngestionJob, context.job_id, populate_existing=True)
                from models import IngestionStatus
                if (job is None or job.status != IngestionStatus.RUNNING
                        or job.dry_run is not False or context.dry_run is not False):
                    raise ValueError("Exact running retained-source job required")
                validate_retained_pdf(session, source, receipt, job,
                    started=aware(job.started_at), finished=datetime.now(timezone.utc))
        for record, entity, evidence in stock_observations:
            if len(evidence) != 1:
                raise ValueError("Missing/ambiguous stock evidence")
            identity = ObservationIdentity(measure="outstanding", entity_id=entity.id,
                geography=entity.canonical_name, period=record.as_at, unit="KES", basis="actual",
                dimensions={"lender": f"Pending Bills — County Governments ({record.entity_name})",
                            "debt_category": "pending_bills"})
            cell = evidence[0]
            q = evaluate_qualification(identity, record.total_pending, source=source,
                evidence=cell, receipt=receipts.get(cell.get("receipt", {}).get("extraction_id")))
            if q.status != "verified" or q.digest != ARTIFACT_SHA256:
                raise ValueError("Unqualified or changed stock artifact")
    except (ValueError, TypeError, KeyError, AttributeError):
        logger.info("Aging pointers cleared: current stock artifact is unqualified")
        return {}
    retained = {}
    for scope, ref in refs.items():
        contract = scope_contract(scope)
        if (not isinstance(ref, dict) or ref.get("publication_batch") != publication_batch
                or ref.get("source_url") != source.url or ref.get("as_at") != AS_AT
                or type(ref.get("extraction_id")) is not int):
            continue
        extraction = session.query(Extraction).populate_existing().filter(
            Extraction.id == ref["extraction_id"], Extraction.source_document_id == source.id,
            Extraction.extractor == contract["extractor"]).one_or_none()
        if extraction is not None and public_observation(
                session, source, extraction, ref, scope=scope)["status"] == "qualified":
            retained[contract["metadata_key"]] = deepcopy(ref)
        else:
            logger.info("Aging pointer cleared: %s retained cohort failed qualification", scope)
    return retained


def _require_current_source(source):
    from models import DocumentStatus

    artifact = source.meta.get("pdf_artifact_v1") if isinstance(source.meta, dict) else None
    if (source.status != DocumentStatus.AVAILABLE
            or source.publisher != "Office of the Controller of Budget (OCOB)"
            or source.country is None or source.country.id != source.country_id
            or source.country.iso_code != "KEN"
            or source.md5 is not None and source.md5 != ARTIFACT_MD5
            or artifact is not None and (not isinstance(artifact, dict)
                or artifact.get("sha256") != ARTIFACT_SHA256
                or artifact.get("md5") != ARTIFACT_MD5)):
        raise ValueError("Current source edition is unavailable or changed")


def validate_cohort(cohort):
    from seeding.pdf_parsers import KENYAN_COUNTIES

    if not isinstance(cohort, dict):
        raise ValueError("Unsupported aging schema")
    contract = scope_contract(cohort.get("scope"))
    if (
        cohort.get("version") != contract["version"]
        or type(cohort.get("version")) is not int
    ):
        raise ValueError("Unsupported aging schema")
    if any(
        cohort.get(k) != v
        for k, v in dict(
            scope=cohort["scope"],
            as_at=AS_AT,
            fiscal_year=FISCAL_YEAR,
            table=contract["table"],
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
        or any(not isinstance(r, dict) for r in rows)
        or {r.get("county") for r in rows} != set(KENYAN_COUNTIES)
    ):
        raise ValueError("Incomplete/duplicated aging cohort")
    reconciliation = cohort.get("reconciliation")
    if (not isinstance(reconciliation, list) or len(reconciliation) != 5
        or any(not isinstance(item, dict) or item.get("column") != column
               or type(item.get("reported_count")) is not int
               or not 0 <= item["reported_count"] <= 47
               or item.get("status") not in {"not_reconciled_missing_cells", "matched_with_rounding", "conflicting"}
               for item, column in zip(reconciliation, (*BANDS, "Total")))):
        raise ValueError("Invalid aging reconciliation")
    for item in reconciliation:
        require_pending_amount(item.get("known_cells_sum"), "aging known sum")
        require_pending_amount(item.get("printed_amount"), "aging printed sum")
    if not isinstance(cohort.get("summary"), dict) or cohort["summary"].get("county") != "Total":
        raise ValueError("Invalid aging summary identity")
    for row in [*rows, cohort.get("summary")]:
        if (
            not isinstance(row, dict)
            or type(row.get("page")) is not int
            or row["page"] not in contract["pages"]
        ):
            raise ValueError("Invalid aging locator")
        notes = row.get("reader_notes")
        if not isinstance(notes, list) or any(
            not isinstance(note, dict) or not isinstance(note.get("code"), str)
            or not note["code"].strip() for note in notes
        ):
            raise ValueError("Invalid aging reader qualifications")
        if not isinstance(row.get("raw_cells"), list) or len(row["raw_cells"]) != 5:
            raise ValueError("Invalid aging cells")
        normalized = (
            [None] * 5
            if row["county"] == "Nandi" and cohort["scope"] == SCOPE
            else [_amount(c) for c in row["raw_cells"]]
        )
        if normalized != row.get("amounts"):
            raise ValueError("Aging raw and normalized cells disagree")
        _validate_reader_notes(row, cohort["scope"], contract)
    if any(value is None for value in cohort["summary"]["amounts"]):
        raise ValueError("Incomplete aging printed summary")
    # Reconciliation describes these retained cells, not independently supplied
    # metadata. A correct fingerprint cannot make a contradictory status true.
    for index, item in enumerate(reconciliation):
        present = [Decimal(row["amounts"][index]) for row in rows
                   if row["amounts"][index] is not None]
        known_sum = sum(present, Decimal(0))
        printed = Decimal(cohort["summary"]["amounts"][index])
        status = ("not_reconciled_missing_cells" if len(present) != 47
                  else "matched_with_rounding" if abs(known_sum - printed) <= Decimal(500000)
                  else "conflicting")
        if (require_pending_amount(item["known_cells_sum"], "aging known sum") != known_sum
            or require_pending_amount(item["printed_amount"], "aging printed sum") != printed
            or item["reported_count"] != len(present) or item["status"] != status):
            raise ValueError("Aging reconciliation disagrees with retained cells")


def _validate_reader_notes(row, scope, contract):
    """Only source-supported warnings with usable comparison operands qualify."""
    population, table = contract["population"], contract["table"]
    notes = row["reader_notes"]
    codes = [note["code"] for note in notes]
    missing = any(value is None for value in row["amounts"])
    differs = not missing and abs(sum(Decimal(value) for value in row["amounts"][:4])
                                 - Decimal(row["amounts"][4])) > Decimal(50000)
    publisher_absence = scope == SCOPE and row["county"] == "Nandi"
    required = {
        "missing_source_cells": missing,
        "bands_differ_from_printed_total": differs,
        "publisher_says_aging_not_provided": publisher_absence,
    }
    if len(codes) != len(set(codes)) or any((code in codes) != needed for code, needed in required.items()):
        raise ValueError("Missing or contradictory aging reader qualification warning")
    for note in notes:
        code = note["code"]
        fields = {"code", "table"}
        if code == "publisher_says_aging_not_provided":
            fields |= {"page", "county"}
            if note.get("page") != 54 or type(note.get("page")) is not int or note.get("county") != "Nandi":
                raise ValueError("Invalid publisher aging qualification")
        elif code in {f"payables_{population}_total_differs", f"known_payables_{population}_sum_differs"}:
            summary = code.startswith("known_")
            fields |= {"comparison_table", "comparison_amount"}
            fields |= {"aging_reported_total"} if summary else {"comparison_page"}
            if (summary != (row["county"] == "Total") or note.get("comparison_table") != "Table 2.10"
                or row["amounts"][4] is None or not isinstance(note.get("comparison_amount"), str)
                or re.fullmatch(r"\d+(?:\.\d+)?", note["comparison_amount"]) is None):
                raise ValueError("Invalid aging comparison qualification")
            comparison = require_pending_amount(note["comparison_amount"], "aging comparison")
            if comparison > Decimal("1e18") * (47 if summary else 1):
                raise ValueError("Aging comparison exceeds the supported source range")
            reported = Decimal(row["amounts"][4])
            if abs(comparison - reported) <= Decimal(500000 if summary else 50000):
                raise ValueError("Aging comparison warning has no discrepancy")
            if summary:
                if (not isinstance(note.get("aging_reported_total"), str)
                    or re.fullmatch(r"\d+(?:\.\d+)?", note["aging_reported_total"]) is None
                    or require_pending_amount(note["aging_reported_total"], "aging reported total") != reported):
                    raise ValueError("Aging comparison total disagrees with retained cells")
            elif type(note.get("comparison_page")) is not int or note["comparison_page"] not in (51, 52, 53):
                raise ValueError("Invalid aging comparison page")
        elif code not in {"missing_source_cells", "bands_differ_from_printed_total", "cob_marked_inconsistent"}:
            raise ValueError("Unsupported aging reader qualification")
        if set(note) != fields or note.get("table") != table:
            raise ValueError("Invalid aging reader qualification fields/scope")


def public_observation(db, source, extraction, ref, *, county=None, scope=SCOPE):
    from services.figure_qualification import (
        ObservationIdentity,
        evaluate_qualification,
    )

    cohort = extraction.extracted_json
    try:
        _require_current_source(source)
        validate_cohort(cohort)
        if cohort["scope"] != scope:
            raise ValueError("Aging population mismatch")
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
            return absent_observation(scope, "county_not_in_aging_cohort")
        all_rows = [*cohort["rows"], cohort["summary"]]
        ids = {
            e.get("receipt", {}).get("extraction_id")
            for r in all_rows
            for e in r.get("source_evidence", [])
        }
        receipts = {
            e.id: e.extracted_json.get("response_receipt")
            for e in db.query(Extraction)
            .populate_existing()
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
                    if e.get("identity") == _identity(checked_row, column, scope)
                ]
                if len(matches) != 1:
                    raise ValueError("Missing/ambiguous aging cell evidence")
                cell = matches[0]
                q = evaluate_qualification(
                    ObservationIdentity(**_identity(checked_row, column, scope)),
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
        return absent_observation(scope, "invalid_or_unqualified_aging_evidence")
    missing = [r["county"] for r in cohort["rows"] if r["amounts"][4] is None]
    qualified = [r["county"] for r in cohort["rows"] if r["reader_notes"]]
    notes = deepcopy(row["reader_notes"])
    if not county:
        notes.append({"code": f"reported_{scope.removeprefix('county_')}_population_only", "table": cohort["table"]})
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
        version=cohort["version"],
        scope=scope,
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
        table=cohort["table"],
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
            counties_with_all_bands=sum(all(v is not None for v in r["amounts"][:4]) for r in cohort["rows"]),
            missing_band_counties=[r["county"] for r in cohort["rows"] if any(v is None for v in r["amounts"][:4])],
        ),
        reader_notes=notes,
        reconciliation=cohort["reconciliation"],
        qualifications=qualifications,
        chart_supported=all(b["amount"] is not None for b in buckets)
        and not any(n["code"] == "bands_differ_from_printed_total" for n in notes),
    )
