"""Writer for fiscal summary records to database."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from models import Country, DocumentType, FiscalSummary, SourceDocument
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from .parser import FiscalSummaryRecord

logger = logging.getLogger("seeding.fiscal_summary.writer")


def _get_or_create_source_document(
    session: Session, metadata: dict[str, Any]
) -> SourceDocument:
    """Get or create source document for fiscal summary data."""
    title = metadata.get(
        "source", "National Treasury BPS & Controller of Budget Reports"
    )

    doc = (
        session.query(SourceDocument)
        .filter(
            SourceDocument.title == title,
            SourceDocument.doc_type == DocumentType.REPORT,
        )
        .first()
    )
    if doc:
        return doc

    kenya = session.query(Country).filter(Country.iso_code == "KEN").first()
    if not kenya:
        raise ValueError("Kenya country not found. Run bootstrap_data.py first.")

    doc = SourceDocument(
        country_id=kenya.id,
        publisher="National Treasury & Controller of Budget",
        title=title,
        url="https://www.treasury.go.ke/budget-policy-statement/",
        fetch_date=datetime.now(timezone.utc),
        doc_type=DocumentType.REPORT,
        meta={
            "notes": metadata.get("notes", ""),
            "units": metadata.get("units", "billions_kes"),
        },
    )
    session.add(doc)
    session.flush()
    return doc


def _raw_kes(value: Any) -> Any:
    """Normalise a money value to raw KES at the DB boundary.

    Parser records (and fixtures) carry the historical billions convention;
    the table stores raw KES with a declared ``unit`` column since the
    stage1 3a migration. No national fiscal aggregate legitimately sits
    between 1e6 and 1e9, so the scale test is unambiguous and idempotent.
    """
    if value is None:
        return None
    # A bool is an int in Python and would silently become 1e9 KES; NaN/inf
    # would poison the table. Both are parser bugs — fail closed, loudly.
    if isinstance(value, bool):
        raise ValueError(f"boolean is not a money value: {value!r}")
    v = float(value)
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(f"non-finite money value: {value!r}")
    if v < 0:
        raise ValueError("negative money value")
    return round(v * 1e9 if v < 1_000_000 else v, 2)


def _budget_basis_meta(record) -> dict[str, Any]:
    """``metadata`` payload recording WHICH measure each figure is, and where
    it came from: the budget basis and its receipt, the debt-service figure's
    own source, and the fiscal-framework split with its own total, basis and
    receipt.

    The debt-service source is recorded independently of the budget basis,
    because the two figures can come from different documents (#235).

    Each part is written only when the record carries it, so a row that was
    never sourced cannot come out of here looking as if it had been.
    Stored in the existing JSONB column rather than new ones: this needs no
    migration, so it cannot add to the production schema drift.
    """
    out: dict[str, Any] = {}
    for key in ("fiscal_measure_contract", "tax_split_observation"):
        value = getattr(record, key, None)
        if isinstance(value, dict):
            out[key] = value
    retained=getattr(record,"retained_measure_fields",None)
    if retained:
        out["retained_measure_fields"]=list(retained)
    ds_source = getattr(record, "debt_service_source", None)
    if isinstance(ds_source, dict):
        out["debt_service_source"] = ds_source
    revenue_source = getattr(record, "revenue_source", None)
    if isinstance(revenue_source, dict):
        out["revenue_source"] = revenue_source
    basis = getattr(record, "budget_basis", None)
    if basis:
        out["budget_basis"] = basis
        source = getattr(record, "budget_basis_source", None)
        if isinstance(source, dict):
            out["budget_basis_source"] = source
        redemption = getattr(record, "debt_redemption", None)
        if redemption is not None:
            out["debt_redemption_billion"] = redemption

    framework = getattr(record, "fiscal_framework", None)
    if isinstance(framework, dict):
        out["fiscal_framework"] = framework
    for key in ("split_basis", "fiscal_framework_absent_reason", "tax_split_absent_reason"):
        value = getattr(record, key, None)
        if value:
            out[key] = value
    return out


def _actual_source_candidates(session, country_id, url, digest):
    matches = session.query(SourceDocument).filter(SourceDocument.url == url).all()
    matches = [doc for doc in matches
               if isinstance(doc.meta, dict) and doc.meta.get("source_sha256") == digest]
    if len(matches)>1 or any(d.country_id!=country_id or d.publisher!="The National Treasury" for d in matches):
        raise ValueError("ambiguous fiscal source association")
    return matches


def _persist_actual_source(session, record, meta):
    """Persist only the existing common acquisition capability, never exported JSON.

    Original acquisition timestamps survive replay. A cached body without its
    original authority creates no new SourceDocument or claimed acquisition.
    """
    from services.response_receipts import receipt_is_sealed, persist_evidence
    evidence=getattr(record, "source_evidence", None) or []
    if not evidence:
        return None
    receipt=evidence[0].get("_response_receipt")
    if not receipt_is_sealed(receipt):
        raise ValueError("fiscal source evidence requires sealed acquisition")
    from .actuals import APDMR_URL, APDMR_SHA256
    if receipt.get("digest") != APDMR_SHA256 or receipt.get("request_url") != APDMR_URL:
        raise ValueError("fiscal source acquisition identity disagrees")
    acquired=datetime.fromisoformat(receipt["acquired_at"])
    kenya=session.query(Country).filter(Country.iso_code == "KEN").one()
    matches=_actual_source_candidates(session, kenya.id, APDMR_URL, APDMR_SHA256)
    doc=matches[0] if matches else None
    if doc is None:
        doc=SourceDocument(country_id=kenya.id,publisher="The National Treasury",
            title="Annual Public Debt Management Report FY2022/2023 (September 2023)",
            url=APDMR_URL,fetch_date=acquired,doc_type=DocumentType.REPORT,
            meta={"source_sha256":APDMR_SHA256,"original_acquisition_at":receipt["acquired_at"]})
        session.add(doc);session.flush()
    persisted=persist_evidence(session,doc,evidence)
    from models import Extraction
    for observation in persisted:
        extraction=session.get(Extraction,observation["receipt"]["extraction_id"])
        stored=extraction.extracted_json.get("response_receipt",{})
        if (stored.get("byte_check",{}).get("status") != "matched"
                or stored.get("digest") != APDMR_SHA256):
            raise ValueError("fiscal acquisition retention unconfirmed")
    meta["source_evidence"]=persisted
    proofs=(meta.get("fiscal_measure_contract") or {}).get("measures",{})
    for observation in persisted:
        field=observation["identity"]["measure"]
        if field in proofs:
            proofs[field]["source_document_id"]=doc.id
            proofs[field]["extraction_id"]=observation["receipt"]["extraction_id"]
    return doc


def _persist_historical_outturn(session, record, meta):
    """Keep the two Treasury PDFs and their observations in the same savepoint."""
    evidence = getattr(record, "historical_outturn_evidence", None)
    if evidence is None:
        return
    from models import Extraction
    from services.response_receipts import persist_evidence, receipt_is_sealed
    from .historical_outturn import EDITIONS, YEAR

    if record.fiscal_year != YEAR or not isinstance(evidence, list):
        raise ValueError("invalid historical outturn receipt scope")
    groups = {url: [] for url in EDITIONS}
    for item in evidence:
        receipt = item.get("_response_receipt")
        if not receipt_is_sealed(receipt) or receipt.get("request_url") not in groups:
            raise ValueError("historical outturn requires sealed official acquisitions")
        groups[receipt["request_url"]].append(item)

    kenya = session.query(Country).filter(Country.iso_code == "KEN").one()
    proofs = meta["fiscal_measure_contract"]["measures"]
    for url, items in groups.items():
        digest, page, title, parser, fields = EDITIONS[url]
        if len(items) != len(fields) or {item["identity"]["measure"] for item in items} != fields:
            raise ValueError("historical outturn observation inventory changed")
        for item in items:
            receipt = item["_response_receipt"]
            field = item["identity"]["measure"]
            source = proofs[field]["source"]
            if (
                receipt.get("digest") != digest or receipt.get("request_url") != url
                or receipt.get("response_url") != url or receipt.get("status") != 200
                or receipt.get("parser_version") != parser or item["locator"]["page"] != page
                or receipt.get("byte_check", {}).get("status") != "matched"
                or {k: v for k, v in item.items() if k != "_response_receipt"} not in receipt["observations"]
                or item["identity"]["period"] != YEAR or item["identity"]["basis"] != proofs[field]["basis"]
                or item["identity"]["geography"] != "KEN" or item["identity"]["unit"] != "KES"
                or item["identity"]["dimensions"] != {"vintage": "Actual"}
                or item["value"] != str(proofs[field]["value_kes"])
                or source["url"] != url or source["sha256"] != digest
            ):
                raise ValueError("historical outturn observation differs from its receipt")
        matches = _actual_source_candidates(session, kenya.id, url, digest)
        if matches:
            doc = matches[0]
        else:
            acquired_at = items[0]["_response_receipt"]["acquired_at"]
            doc = SourceDocument(country_id=kenya.id, publisher="The National Treasury",
                                 title=title, url=url, fetch_date=datetime.fromisoformat(acquired_at),
                                 doc_type=DocumentType.REPORT,
                                 meta={"source_sha256": digest, "original_acquisition_at": acquired_at})
            session.add(doc)
            session.flush()
        persisted = persist_evidence(session, doc, items)
        for observation in persisted:
            association = observation["receipt"]
            extraction_id = association.get("extraction_id")
            extraction = session.get(Extraction, extraction_id) if extraction_id else None
            if (extraction is None or extraction.source_document_id != doc.id
                    or extraction.page_number != page or association.get("digest") != digest
                    or extraction.extracted_json["response_receipt"]["byte_check"]["status"] != "matched"):
                raise ValueError("historical outturn receipt could not be retained")
            field = observation["identity"]["measure"]
            proofs[field].update(source_document_id=doc.id, extraction_id=extraction.id)
        meta.setdefault("source_evidence", []).extend(persisted)


def _preserve_actual_lineage(session, existing, meta):
    """Keep an exact earlier association without asserting a new acquisition."""
    if existing is None or not isinstance(existing.meta, dict):
        return None
    from models import Extraction
    from .actuals import APDMR_SHA256, APDMR_URL
    before=(existing.meta.get("fiscal_measure_contract") or {}).get("measures",{})
    after=(meta.get("fiscal_measure_contract") or {}).get("measures",{})
    for field in ("total_revenue","debt_service_cost"):
        old,new=before.get(field),after.get(field)
        if not isinstance(old,dict) or not isinstance(new,dict):
            return None
        if any(old.get(k)!=new.get(k) for k in ("value_kes","fiscal_year","basis","vintage","precision_kes","source")):
            return None
        if new["source"].get("sha256") != APDMR_SHA256 or new["source"].get("url") != APDMR_URL:
            return None
        identity=old.get("extraction_id")
        if type(identity) is not int or identity<=0:
            return None
        if type(old.get("source_document_id")) is not int or old["source_document_id"]<=0:
            raise ValueError("retained fiscal source identity invalid")
        if existing.source_document_id!=old["source_document_id"]:
            raise ValueError("retained fiscal primary source association disagrees")
        extraction=session.get(Extraction,identity)
        if (extraction is None or extraction.extractor!="pdf-receipt-v1"
                or extraction.page_number!=37
                or extraction.source_document_id!=old.get("source_document_id")):
            raise ValueError("retained fiscal extraction association missing")
        receipt=extraction.extracted_json.get("response_receipt",{})
        observations=receipt.get("observations",[])
        if (receipt.get("digest")!=APDMR_SHA256
                or receipt.get("parser_version")!="fiscal-apdmr-actuals-v1"
                or receipt.get("byte_check",{}).get("status")!="matched"
                or not any(o.get("identity",{}).get("measure")==field
                           and o["identity"].get("period")==existing.fiscal_year
                           and o["identity"].get("basis")==new["basis"]
                           and o["identity"].get("unit")=="KES"
                           and o["identity"].get("geography")=="KEN"
                           and o["identity"].get("dimensions",{}).get("vintage")==new["vintage"]
                           and o.get("value")==str(new["value_kes"]) for o in observations)):
            raise ValueError("retained fiscal source observation disagrees")
        new["source_document_id"]=old["source_document_id"]
        new["extraction_id"]=identity
    doc=session.get(SourceDocument,after["total_revenue"]["source_document_id"])
    kenya=session.query(Country).filter(Country.iso_code == "KEN").one()
    matches=_actual_source_candidates(session, kenya.id, APDMR_URL, APDMR_SHA256)
    if doc is None or len(matches)!=1 or matches[0].id!=doc.id:
        raise ValueError("retained fiscal document association missing")
    meta["source_evidence"]=existing.meta.get("source_evidence",[])
    return doc


def _retain_last_good(record, existing):
    """An unavailable refresh cannot downgrade already qualified observations."""
    if existing is None:
        return record
    from copy import copy, deepcopy
    from services.fiscal_qualification import fiscal_values, published_framework, VERSION
    values=fiscal_values(existing)
    proofs=values["measure_qualifications"]
    result=copy(record)
    contract=deepcopy(getattr(record,"fiscal_measure_contract",None) or {"version":VERSION,"measures":{}})
    retained=[]
    for field,proof in proofs.items():
        if field in contract["measures"]:
            continue
        if field in ("tax_revenue","non_tax_revenue") and getattr(record,"tax_split_absent_reason",None):
            continue
        setattr(result,field,values[field]/1e9)
        contract["measures"][field]=deepcopy(proof)
        retained.append(field)
        source_field={"appropriated_budget":"budget_basis_source","total_revenue":"revenue_source","debt_service_cost":"debt_service_source"}.get(field)
        if source_field:
            setattr(result,source_field,deepcopy(proof["source"]))
    if retained:
        result.fiscal_measure_contract=contract
        result.retained_measure_fields=retained
    if "appropriated_budget" in retained:
        result.budget_basis=(existing.meta or {}).get("budget_basis")
    candidate_framework = getattr(result, 'fiscal_framework', None)
    from types import SimpleNamespace
    candidate_public = published_framework(SimpleNamespace(
        fiscal_year=result.fiscal_year, meta={'fiscal_framework': candidate_framework}))
    if candidate_public is None:
        framework=published_framework(existing)
        if framework is not None:
            # Preserve the original per-cell proofs; the public serialization
            # deliberately excludes parser input and cannot be re-ingested.
            result.fiscal_framework=deepcopy(existing.meta["fiscal_framework"])
            result.split_basis="treasury_fiscal_framework"
            result.fiscal_framework_absent_reason=None
            result.retained_measure_fields = [*retained, 'fiscal_framework']
    if getattr(result,"tax_split_observation",None) is None:
        result.tax_split_observation=deepcopy((existing.meta or {}).get("tax_split_observation"))
    return result


def _require_historical_acquisition(record, contract, framework):
    from .historical_outturn import EDITIONS

    if getattr(record, "historical_outturn_evidence", None) is not None:
        return
    source_claims = []
    if isinstance(framework, dict):
        source_claims.append(framework.get("source"))
    if isinstance(contract, dict) and isinstance(contract.get("measures"), dict):
        source_claims.extend(proof.get("source") for proof in contract["measures"].values()
                             if isinstance(proof, dict))
    reviewed_digests = tuple(edition[0] for edition in EDITIONS.values())
    reviewed_urls = tuple(EDITIONS)
    if any(isinstance(source, dict)
           and (source.get("url") in reviewed_urls or source.get("sha256") in reviewed_digests)
           for source in source_claims):
        raise ValueError("historical fiscal source claims require both sealed acquisitions")


def write_fiscal_summary_records(session, records, metadata):
    """A rejected batch cannot leave a partially overwritten fiscal series."""
    from services.fiscal_qualification import fiscal_year_key
    records=list(records)
    seen=set()
    for record in records:
        if not isinstance(record.fiscal_year,str):
            raise ValueError("invalid fiscal year")
        key=fiscal_year_key(record.fiscal_year) or record.fiscal_year
        if key in seen:
            raise ValueError("duplicate fiscal year in writer batch")
        seen.add(key)
        from services.fiscal_framework_qualification import validate_framework_contract
        validate_framework_contract(getattr(record, 'fiscal_framework', None), record.fiscal_year)
        from services.fiscal_qualification import MONEY_BASES
        for field in MONEY_BASES:
            _raw_kes(getattr(record,field,None))
        contract=getattr(record,"fiscal_measure_contract",None)
        _require_historical_acquisition(record, contract, getattr(record, "fiscal_framework", None))
        if contract is not None:
            from services.fiscal_qualification import VERSION, MONEY_BASES
            if (not isinstance(contract,dict) or contract.get("version")!=VERSION
                    or not isinstance(contract.get("measures"),dict)):
                raise ValueError("unknown or malformed fiscal measure contract")
            from services.fiscal_outturns import finite_number
            for field,proof in contract["measures"].items():
                if field not in MONEY_BASES or not isinstance(proof,dict):
                    raise ValueError("invalid fiscal measure proof")
                amount=_raw_kes(getattr(record,field,None))
                witnessed=finite_number(proof.get("value_kes"))
                if amount is None or witnessed is None or amount!=witnessed:
                    raise ValueError("fiscal measure proof contradicts writer amount")
                from types import SimpleNamespace
                from services.fiscal_qualification import qualify_measure
                row=SimpleNamespace(fiscal_year=record.fiscal_year,unit="KES",
                    meta={"fiscal_measure_contract":contract},**{field:amount})
                if qualify_measure(row,field)[2] is not None:
                    raise ValueError("invalid fiscal measure proof semantics")
    with session.begin_nested():
        return _write_fiscal_summary_records(session, records, metadata)


def _write_fiscal_summary_records(
    session: Session,
    records: list[FiscalSummaryRecord],
    metadata: dict[str, Any],
) -> tuple[int, int]:
    """Upsert fiscal summary records into the database (raw KES)."""
    created = 0
    updated = 0
    if not records:
        return created, updated

    from services.fiscal_historical_sources import OUTTURN_SHA256, OUTTURN_URL, YEAR

    source_doc = _get_or_create_source_document(session, metadata)

    for record in records:
        existing = (
            session.query(FiscalSummary)
            .filter(FiscalSummary.fiscal_year == record.fiscal_year)
            .first()
        )

        if (existing is not None and record.fiscal_year == YEAR
                and getattr(record, "historical_outturn_evidence", None) is None):
            from services.fiscal_qualification import published_framework

            framework = published_framework(existing)
            source = framework["source"] if framework is not None else {}
            if source.get("url") == OUTTURN_URL and source.get("sha256") == OUTTURN_SHA256:
                # Preserve a previously qualified pair atomically. Legacy
                # rows continue through the existing per-measure retention.
                updated += 1
                continue

        record=_retain_last_good(record,existing)

        fields = {
            # Money columns: converted to raw KES at this boundary.
            "appropriated_budget": _raw_kes(record.appropriated_budget),
            "total_revenue": _raw_kes(record.total_revenue),
            "tax_revenue": _raw_kes(record.tax_revenue),
            "non_tax_revenue": _raw_kes(record.non_tax_revenue),
            "total_borrowing": _raw_kes(record.total_borrowing),
            "borrowing_pct_of_budget": record.borrowing_pct_of_budget,
            "debt_service_cost": _raw_kes(record.debt_service_cost),
            "debt_service_per_shilling": record.debt_service_per_shilling,
            "debt_ceiling": _raw_kes(record.debt_ceiling),
            "actual_debt": _raw_kes(record.actual_debt),
            "debt_ceiling_usage_pct": record.debt_ceiling_usage_pct,
            "development_spending": _raw_kes(record.development_spending),
            "recurrent_spending": _raw_kes(record.recurrent_spending),
            "county_allocation": _raw_kes(record.county_allocation),
            "unit": "KES",
        }

        # Provenance for the budget figure. Persisted so the API can say
        # WHICH measure it is publishing — "no number without provenance"
        # applies to a number's definition, not only its value.
        basis_meta = _budget_basis_meta(record)
        actual_source_doc = _persist_actual_source(session, record, basis_meta)
        actual_source_doc = actual_source_doc or _preserve_actual_lineage(session, existing, basis_meta)
        _persist_historical_outturn(session, record, basis_meta)
        row_source_doc = actual_source_doc or source_doc
        fields["meta"] = basis_meta
        fields["page_ref"] = None
        if basis_meta:
            # The row locator must describe its primary linked document.
            # Every other measure still carries its independent source proof.
            measures=(basis_meta.get("fiscal_measure_contract") or {}).get("measures",{})
            page_ref = None
            if actual_source_doc:
                for proof in measures.values():
                    if isinstance(proof,dict) and proof.get("source_document_id")==actual_source_doc.id:
                        page_ref=proof["source"]["page"]
                        break
            else:
                page_ref = (basis_meta.get("budget_basis_source") or {}).get("page") or (
                    (basis_meta.get("fiscal_framework") or {}).get("source") or {}
                ).get("page")
            if not page_ref:
                for proof in measures.values():
                    if isinstance(proof,dict):
                        from services.fiscal_qualification import valid_source
                        if valid_source(proof.get("source")):
                            page_ref=proof["source"]["page"]
                            break
            if page_ref:
                fields["page_ref"] = str(page_ref)[:50]

        if existing:
            for key, val in fields.items():
                setattr(existing, key, val)
            existing.source_document_id = row_source_doc.id
            existing.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            row = FiscalSummary(
                fiscal_year=record.fiscal_year,
                source_document_id=row_source_doc.id,
                **fields,
            )
            session.add(row)
            created += 1

    session.flush()
    logger.info(f"Fiscal summary: {created} created, {updated} updated")
    return created, updated
