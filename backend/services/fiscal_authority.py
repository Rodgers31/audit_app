"""Actual-PostgreSQL semantic adapter for the acceptance lane.

This observes publication qualifications and retained associations, not release,
issuer approval or financial adoption. Those authorities remain independent.
No caller-provided verdict or attachment hash can replace database observations.
"""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import text
from sqlalchemy.orm import Session
from models import Country, DebtTimeline, DocumentType, Extraction, FiscalSummary, SourceDocument
from services.fiscal_qualification import fiscal_values, fiscal_year_key, published_tax_observation
from services.fiscal_framework_qualification import qualified_framework
from services.financial_publication import fiscal_history_entry
from seeding.domains.debt_timeline.coverage import coverage_report
from seeding.domains.debt_timeline.publication import public_debt_rows

CONTRACT = "fiscal-debt-authority-observations-v1"


def _expected_periods(fiscal_years, debt_years):
    if (type(fiscal_years) is not list or not fiscal_years
            or any(fiscal_year_key(fy) is None for fy in fiscal_years)):
        raise ValueError("nonempty explicit fiscal-year inventory required")
    years = [fiscal_year_key(fy) for fy in fiscal_years]
    if len(set(years)) != len(years):
        raise ValueError("distinct fiscal-year inventory required")
    if (type(debt_years) is not list or not debt_years
            or any(type(y) is not int or not 1900 <= y <= 9999 for y in debt_years)
            or len(set(debt_years)) != len(debt_years)):
        raise ValueError("nonempty distinct calendar-year inventory required")
    return sorted(years), sorted(debt_years)


def _retained_fiscal_association(db, proof, *, field=None, receipt_store=None, original_cache=None):
    """Validate a known parser's actual retained manifest, then optional originals.

    A metadata association alone is never called original-byte verification.
    Unknown parser/source combinations remain explicit engineering holds.
    """
    from decimal import Decimal, InvalidOperation
    from seeding.domains.fiscal_summary.actuals import APDMR_URL, APDMR_SHA256, FY
    def held(state, reason):
        return {"state": state, "reason": reason}
    document_id, extraction_id = proof.get("source_document_id"), proof.get("extraction_id")
    if any(type(v) is not int or v <= 0 for v in (document_id, extraction_id)):
        return held("unconfirmed", "original_document_and_extraction_association_required")
    document, extraction = db.get(SourceDocument, document_id), db.get(Extraction, extraction_id)
    source = proof.get("source")
    receipt = extraction.extracted_json.get("response_receipt") if extraction and isinstance(extraction.extracted_json, dict) else None
    byte_check = receipt.get("byte_check") if isinstance(receipt, dict) else None
    if (document is None or extraction is None or extraction.source_document_id != document.id
            or not isinstance(source, dict) or document.url != source.get("url")
            or not isinstance(receipt, dict) or receipt.get("digest") != source.get("sha256")
            or not isinstance(byte_check, dict) or byte_check.get("status") != "matched"):
        return held("conflicting", "retained_fiscal_association_disagrees")
    if source.get("url") != APDMR_URL or source.get("sha256") != APDMR_SHA256:
        return held("unconfirmed", "reviewed_source_parser_and_retention_adapter_required")
    country = db.get(Country, document.country_id)
    if (field not in {"total_revenue", "debt_service_cost"} or country is None or country.iso_code != "KEN"
            or document.publisher != "The National Treasury" or document.doc_type != DocumentType.REPORT
            or document.title != "Annual Public Debt Management Report FY2022/2023 (September 2023)"
            or source.get("title") != document.title or source.get("publisher") != document.publisher
            or not isinstance(document.meta, dict) or document.meta.get("source_sha256") != APDMR_SHA256
            or extraction.extractor != "pdf-receipt-v1" or extraction.page_number != 37
            or receipt.get("parser_version") != "fiscal-apdmr-actuals-v1" or receipt.get("source_kind") != "pdf"
            or type(receipt.get("status")) is not int or receipt["status"] != 200
            or not isinstance(receipt.get("content_type"), str) or "pdf" not in receipt["content_type"].lower()
            or receipt.get("request_url") != APDMR_URL or receipt.get("response_url") != APDMR_URL
            or byte_check.get("sha256") != APDMR_SHA256
            or type(receipt.get("byte_size")) is not int or not 0 < receipt["byte_size"] <= 10_000_000
            or not receipt.get("storage_key") or not isinstance(receipt.get("acquired_at"), str)
            or source.get("page") != "Table 4.1-1, PDF p.37" or source.get("column") != "Preliminary"
            or fiscal_year_key(proof.get("fiscal_year")) != FY or proof.get("vintage") != "Preliminary"
            or proof.get("precision_kes") != 1_000_000):
        return held("conflicting", "retained_fiscal_parser_or_source_identity_disagrees")
    observations = receipt.get("observations")
    matches = [o for o in observations if isinstance(o, dict) and isinstance(o.get("identity"), dict)
               and o["identity"].get("measure") == field] if isinstance(observations, list) else []
    if len(matches) != 1:
        return held("conflicting", "retained_fiscal_observation_missing_or_ambiguous")
    observed = matches[0]
    identity, locator = observed["identity"], observed.get("locator")
    expected_basis = {"total_revenue": "ordinary_revenue_excl_aia",
                      "debt_service_cost": "total_debt_service_interest_and_principal"}[field]
    try:
        def number(v):
            if isinstance(v, bool) or not isinstance(v, (int, float, str, Decimal)):
                raise ValueError("numeric witness required")
            value = Decimal(str(v))
            if not value.is_finite() or value < 0:
                raise ValueError("finite nonnegative witness required")
            return value
        value = number(proof.get("value_kes"))
        numbers_match = number(observed.get("value")) == value == number(observed.get("raw_value")) * 1_000_000
    except (ValueError, InvalidOperation):
        numbers_match = False
    checks = observed.get("checks")
    if (not numbers_match or observed.get("source_kind") != "pdf" or observed.get("unit") != "KES"
            or identity.get("entity_id") is not None or identity.get("geography") != "KEN"
            or fiscal_year_key(identity.get("period")) != FY or identity.get("unit") != "KES"
            or identity.get("basis") != expected_basis or proof.get("basis") != expected_basis
            or identity.get("dimensions") != {"vintage": "Preliminary"}
            or locator != {"page": 37, "table": "Table 4.1-1", "cell": field + " / Jun-23*"}
            or observed.get("raw_unit") != "million_KES"
            or observed.get("transformation") != {"operation": "multiply", "factor": "1000000"}
            or not isinstance(checks, dict) or any(checks.get(k) is not True for k in ("identity", "value", "transport", "bytes", "locator"))
            or not isinstance(observed.get("reconciliation"), dict) or observed["reconciliation"].get("status") != "matched"):
        return held("conflicting", "retained_fiscal_observation_semantics_disagree")
    result = {"state": "retained_manifest_observation_bound", "document_id": document.id,
        "extraction_id": extraction.id, "digest": receipt["digest"], "acquired_at": receipt["acquired_at"],
        "manifest_observation": {"measure": field, "value_kes": str(observed["value"]),
            "period": identity["period"], "unit": "KES", "basis": expected_basis, "vintage": "Preliminary",
            "precision_kes": 1_000_000, "locator": deepcopy(locator), "parser_version": receipt["parser_version"]},
        "original_bytes_checked_this_observation": False,
        "reason": "bound_original_receipt_reader_required"}
    if receipt_store is None:
        return result
    cache = original_cache if original_cache is not None else {}
    if APDMR_SHA256 not in cache:
        try:
            from hashlib import sha256
            from io import BytesIO
            import pdfplumber
            from seeding.domains.fiscal_summary.actuals import parse_apdmr_table
            body = receipt_store.read(APDMR_SHA256)
            if type(body) is not bytes or not 0 < len(body) <= 10_000_000 or sha256(body).hexdigest() != APDMR_SHA256:
                raise ValueError("original byte identity refused")
            with pdfplumber.open(BytesIO(body)) as pdf:
                if len(pdf.pages) < 37:
                    raise ValueError("original page inventory refused")
                parsed = parse_apdmr_table(pdf.pages[0].extract_text() or "", pdf.pages[36].extract_text() or "")
            cache[APDMR_SHA256] = (len(body), parsed)
        except (FileNotFoundError, TimeoutError, ConnectionError, OSError):
            cache[APDMR_SHA256] = {"state": "unconfirmed", "reason": "retained_original_readback_unavailable"}
        except ImportError:
            cache[APDMR_SHA256] = {"state": "unconfirmed", "reason": "native_original_parser_runtime_unavailable"}
        except Exception:
            cache[APDMR_SHA256] = {"state": "conflicting", "reason": "retained_original_byte_readback_or_native_parser_refused"}
    original = cache[APDMR_SHA256]
    if isinstance(original, dict):
        return held(original["state"], original["reason"])
    selected = "Ordinary Revenue" if field == "total_revenue" else "Total Debt Service"
    if original[0] != receipt["byte_size"] or Decimal(str(original[1][selected])) * 1_000_000_000 != value:
        return held("conflicting", "retained_original_native_value_disagrees")
    result.update(state="retained_observation_bound", original_bytes_checked_this_observation=True,
                  reason="native_original_and_manifest_match_origin_issuer_and_adoption_authority_still_held")
    return result


def verify_fiscal_debt_authority(db, *, fiscal_years, debt_years, now=None, receipt_store=None):
    """Read actual persisted/public semantics; never certify source adoption.

    Expected inventories are mandatory so omitted historical periods cannot
    disappear behind a successful empty/subset observation. The caller binds
    this report to its exact plan, source/runtime and independently owned PG.
    """
    fiscal_years, debt_years = _expected_periods(fiscal_years, debt_years)
    if not isinstance(db, Session) or db.get_bind().dialect.name != "postgresql":
        raise ValueError("actual PostgreSQL session required for authority observations")
    if db.new or db.dirty or db.deleted:
        raise ValueError("clean persisted session required; pending or dirty changes are not observations")
    now = now or datetime.now(timezone.utc)
    if any(y > now.year for y in debt_years):
        raise ValueError("future stock years are not observed debt periods")
    with db.no_autoflush:
        # Expiration reads the store again without flushing a cached preimage.
        db.expire_all()
        original_cache = {}
        identity = db.execute(text("select current_database(), current_user, inet_server_addr()::text")).one()
        stored = db.query(FiscalSummary).all()
        by_year = {}
        for row in stored:
            fy = fiscal_year_key(row.fiscal_year)
            if fy in fiscal_years:
                if fy in by_year:
                    raise ValueError("ambiguous stored fiscal-year identity")
                by_year[fy] = row
        fiscal, holds = [], []
        for year in fiscal_years:
            row = by_year.get(year)
            if row is None:
                fiscal.append({"fiscal_year": year, "state": "missing"})
                holds.append({"component": "fiscal_summary", "period": year, "reason": "required_row_missing"})
                continue
            values = fiscal_values(row)
            framework, reason = qualified_framework(row)
            associations = {field: _retained_fiscal_association(
                db, proof, field=field, receipt_store=receipt_store, original_cache=original_cache)
                for field, proof in values["measure_qualifications"].items()}
            framework_associations = {field: _retained_fiscal_association(
                db, proof, field=field, receipt_store=receipt_store, original_cache=original_cache)
                for field, proof in (framework or {}).get("measure_qualifications", {}).items()}
            for namespace, group in (("", associations), ("framework.", framework_associations)):
                for field, association in group.items():
                    if association["state"] != "retained_observation_bound":
                        holds.append({"component": "fiscal_summary." + namespace + field + ".source_association",
                                      "period": year, "reason": association["reason"], "state": association["state"]})
            tax_observation = published_tax_observation(row)
            if tax_observation is not None:
                holds.append({"component": "fiscal_summary.tax_split_observation.source_association", "period": year,
                              "reason": "separate_reviewed_transcription_original_and_persisted_lineage_required"})
            fiscal.append({"fiscal_year": year, "row_id": row.id, "unit": row.unit,
                           "page_ref": row.page_ref, "source_document_id": row.source_document_id,
                           "public_values": deepcopy(values), "overview_values": fiscal_history_entry(row),
                           "public_framework": framework, "framework_absent_reason": reason,
                           "retained_associations": associations, "framework_retained_associations": framework_associations,
                           "tax_split_observation": tax_observation})
            holds.extend({"component": field, "period": year, "reason": why}
                         for field, why in values["absent_reasons"].items())
            if reason:
                holds.append({"component": "fiscal_framework", "period": year, "reason": reason})
        rows = db.query(DebtTimeline).filter(DebtTimeline.year.in_(debt_years)).all()
        public = public_debt_rows(db, rows, now=now)
        records = [SimpleNamespace(year=year, external=None, domestic=None, total=None,
                                   gdp=None, source_evidence=[]) for year in debt_years]
        coverage = coverage_report(db, records, now=now)
        for year in coverage["years"]:
            for field, measure in year["measures"].items():
                if measure["state"] not in {"observed_this_run", "retained_qualified"} and not (
                        field == "gdp" and year["year"] >= now.year):
                    holds.append({"component": "debt_timeline." + field, "period": year["year"],
                                  "reason": measure["absence_reason"] or "required_observation_unqualified"})
        return {
            "contract": CONTRACT, "verdict": "PUBLICATION_SEMANTICS_OBSERVED_SOURCE_AUTHORITY_HELD",
            "production_accepted": False, "source_adoption_authorized": False,
            "database": {"dialect": "postgresql", "database": identity[0], "role": identity[1], "server_address": identity[2]},
            "expected_fiscal_years": fiscal_years, "expected_debt_years": debt_years,
            "fiscal": fiscal, "debt": [public[r.id] for r in sorted(rows, key=lambda r: r.year)],
            "debt_coverage": coverage, "holds": holds,
            "independent_requirements": [
                "Exact frozen source/native runtime and actual source-parser replay of retained originals",
                "Authentic original HTTP acquisition and retained-byte readback bound to each accepted observation",
                "Reviewed fiscal edition/precision/basis and exact data-adoption plus visible-withdrawal authority",
                "Actual API/page and signed serving-process refresh acknowledgments on the accepted target",
            ],
        }
