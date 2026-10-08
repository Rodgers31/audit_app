"""Stored, measure-specific qualifications. Public reads never acquire bytes.

Receipt byte checks are performed by ingestion against retained objects. This
reader reports that recorded check, binds it to the observation and refuses
promotion on incomplete, changed or contradictory evidence. Historical rows
remain usable with a qualified citation; their quantities are never rewritten.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, ROUND_HALF_EVEN
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ObservationIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    measure: str
    entity_id: int | None = None
    geography: str
    period: str
    unit: str
    basis: str
    dimensions: dict[str, str | None] = Field(default_factory=dict)


class ReceiptReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    extraction_id: int
    digest: str
    source_document_id: int | None = None


class EvidenceReceipt(BaseModel):
    """Immutable metadata snapshot associated with retained parser input."""

    model_config = ConfigDict(frozen=True, extra="allow", strict=True)
    source_kind: Literal["api", "web", "pdf"]
    status: int | None
    content_type: str | None
    request_url: str
    acquired_at: str | None
    parser_version: str
    digest: str
    byte_size: int
    storage_key: str | None
    byte_check: dict[str, Any]
    observations: list[dict[str, Any]] = Field(default_factory=list)


class ObservationEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow", strict=True)
    version: Literal[1]
    source_kind: Literal["api", "web", "pdf"]
    identity: ObservationIdentity
    receipt: ReceiptReference
    raw_value: Any
    raw_unit: str
    value: Any
    unit: str
    locator: dict[str, Any]
    transformation: dict[str, Any]
    checks: dict[str, bool]
    reconciliation: dict[str, Any]


class FigureQualification(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: Literal[
        "qualified", "verified", "unavailable", "conflicting", "modelled", "projected"
    ]
    reason: str
    source_kind: Literal["api", "web", "pdf", "unknown"] = "unknown"
    identity: ObservationIdentity
    source_document_id: int | None = None
    source_url: str | None = None
    publisher: str | None = None
    receipt_id: int | None = None
    digest: str | None = None
    locator: dict[str, Any] | None = None
    document_bytes_checked: bool = False
    value_checked: bool = False


def _number(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return (
        result
        if result.is_finite() and (result == 0 or -24 <= result.adjusted() <= 24)
        else None
    )


def _enum(value: Any) -> Any:
    return getattr(value, "value", value)


def evaluate_qualification(
    identity: ObservationIdentity,
    value: Any,
    *,
    source: Any = None,
    evidence: Any = None,
    receipt: Any = None,
    origin: str | None = None,
    refusal: str | None = None,
) -> FigureQualification:
    """Pure evaluation over stored evidence; IDs, links and hashes aren't checks."""
    from services.audit_citations import safe_source_url

    stored_url = getattr(source, "url", None)
    url = stored_url if safe_source_url(stored_url) else None
    declared_kind = evidence.get("source_kind") if isinstance(evidence, dict) else None
    if declared_kind not in ("api", "web", "pdf"):
        content_type = getattr(source, "content_type", None)
        declared_kind = (
            "pdf"
            if content_type == "application/pdf"
            else "web"
            if isinstance(content_type, str) and "text/html" in content_type
            else "unknown"
        )
    fields = dict(
        source_kind=declared_kind,
        identity=identity,
        source_document_id=getattr(source, "id", None),
        source_url=url,
        publisher=getattr(source, "publisher", None),
    )

    def result(status, reason, **more):
        return FigureQualification(status=status, reason=reason, **{**fields, **more})

    if value is None:
        return result("unavailable", "value_not_reported")
    if _number(value) is None:
        return result("unavailable", "invalid_numeric_value")
    number = _number(value)
    if identity.unit in ("KES", "billion_KES", "KES_millions") and number < 0:
        return result("unavailable", "negative_monetary_value")
    if identity.measure == "gini_coefficient" and not 0 <= number <= 1:
        return result("unavailable", "gini_outside_coefficient_range")
    if (
        identity.measure
        in ("poverty_headcount_rate", "extreme_poverty_rate", "unemployment_rate")
        and not 0 <= number <= 100
    ):
        return result("unavailable", "rate_outside_percent_range")
    if refusal:
        return result("conflicting", refusal)
    if origin in ("modelled", "modeled", "app_model"):
        return result("modelled", "explicit_model_origin")
    if origin in ("projected", "projection"):
        return result("projected", "explicit_projection")
    if source is None:
        return result("unavailable", "source_document_missing")
    if evidence is None:
        return result(
            "qualified" if url else "unavailable",
            "historical_source_not_value_checked" if url else "source_locator_missing",
        )
    if (
        not isinstance(evidence, dict)
        or type(evidence.get("version")) is not int
        or evidence.get("version") != 1
    ):
        return result("qualified", "invalid_evidence_schema")
    try:
        declared = ObservationIdentity.model_validate(evidence.get("identity"))
    except ValidationError:
        return result("qualified", "invalid_observation_identity")
    if declared != identity:
        return result("conflicting", "observation_identity_mismatch")
    evidence_ref = evidence.get("receipt")
    if (
        not isinstance(evidence_ref, dict)
        or type(evidence_ref.get("extraction_id")) is not int
    ):
        return result("qualified", "receipt_missing")
    receipt_id = evidence_ref["extraction_id"]
    if not isinstance(receipt, dict):
        return result("qualified", "receipt_missing", receipt_id=receipt_id)
    digest = receipt.get("digest") or receipt.get("sha256")
    kind = receipt.get("source_kind")
    if kind not in ("api", "web", "pdf"):
        return result("qualified", "invalid_source_kind", receipt_id=receipt_id)
    detail = dict(receipt_id=receipt_id, source_kind=kind)
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
    ):
        return result("qualified", "invalid_receipt_digest", **detail)
    detail["digest"] = digest
    if evidence_ref.get("digest") != digest:
        return result("conflicting", "receipt_digest_mismatch", **detail)
    byte_check = receipt.get("byte_check")
    if not isinstance(byte_check, dict) or byte_check.get("status") != "matched":
        return result(
            "conflicting"
            if isinstance(byte_check, dict) and byte_check.get("status") == "mismatch"
            else "qualified",
            "retained_bytes_not_matched",
            **detail,
        )
    if byte_check.get("sha256") != digest or not byte_check.get("checked_at"):
        return result("conflicting", "retained_bytes_digest_mismatch", **detail)
    if type(receipt.get("status")) is not int or not 200 <= receipt["status"] < 300:
        return result("qualified", "unsuccessful_response", **detail)
    if (
        not receipt.get("content_type")
        or not receipt.get("acquired_at")
        or not receipt.get("request_url")
        or not receipt.get("parser_version")
    ):
        return result("qualified", "incomplete_receipt", **detail)
    from urllib.parse import urlsplit

    try:
        request = urlsplit(receipt["request_url"])
        registered = urlsplit(url or "")
        host = lambda parsed: (parsed.hostname or "").removeprefix("www.")
        if (
            request.scheme not in ("http", "https")
            or not host(request)
            or not host(registered)
        ):
            return result("qualified", "receipt_request_identity_missing", **detail)
        if host(request) != host(registered):
            if kind == "web":
                return result(
                    "qualified", "embedded_publisher_chain_not_checked", **detail
                )
            return result("conflicting", "receipt_request_source_mismatch", **detail)
        if receipt.get("response_url") and host(
            urlsplit(receipt["response_url"])
        ) != host(request):
            if kind == "web":
                return result(
                    "qualified", "embedded_publisher_chain_not_checked", **detail
                )
            return result("conflicting", "receipt_response_source_mismatch", **detail)
    except (TypeError, ValueError):
        return result("qualified", "invalid_receipt_request_url", **detail)
    size = receipt.get("byte_size", receipt.get("size_bytes"))
    if (
        type(size) is not int
        or size <= 0
        or not receipt.get("storage_key", receipt.get("object_key"))
    ):
        return result("qualified", "retained_object_missing", **detail)
    locator = evidence.get("locator")
    if not isinstance(locator, dict) or not locator:
        return result("qualified", "observation_locator_missing", **detail)
    if kind == "pdf":
        if (
            type(locator.get("page")) is not int
            or locator["page"] < 1
            or not (
                locator.get("table") or locator.get("cell") or locator.get("text_span")
            )
        ):
            return result("qualified", "pdf_locator_missing", **detail)
        if "pdf" not in receipt["content_type"].lower():
            return result("conflicting", "pdf_content_type_mismatch", **detail)
    elif "page" in locator:
        return result("conflicting", "non_pdf_page_locator", **detail)
    elif kind == "api" and not locator.get("json_path"):
        return result("qualified", "api_locator_missing", **detail)
    elif kind == "web" and not (locator.get("table") and locator.get("edition")):
        return result("qualified", "web_edition_locator_missing", **detail)
    # These observations are emitted by the source parser before the writer.
    # Row-level booleans or a normalized row hash cannot certify themselves.
    observations = receipt.get("observations")
    if not isinstance(observations, list) or not observations:
        return result("qualified", "receipt_observation_missing", **detail)
    source_observations = [
        o for o in observations if isinstance(o, dict) and o.get("locator") == locator
    ]
    if len(source_observations) != 1:
        return result("conflicting", "receipt_observation_locator_mismatch", **detail)
    observed = source_observations[0]
    try:
        observed_identity = ObservationIdentity.model_validate(observed.get("identity"))
    except ValidationError:
        return result("qualified", "receipt_observation_identity_missing", **detail)
    if observed_identity.geography != "KEN" and identity.geography != "KEN":

        def county_label(label):
            text = label.removesuffix(" County")
            return "Nairobi" if text == "Nairobi City" else text

        if county_label(observed_identity.geography) == county_label(
            identity.geography
        ):
            observed_identity = observed_identity.model_copy(
                update={"geography": identity.geography}
            )
    if observed_identity.entity_id is None:
        observed_identity = observed_identity.model_copy(
            update={"entity_id": identity.entity_id}
        )
    if (
        observed_identity != identity
        or observed.get("raw_unit") != evidence.get("raw_unit")
        or _number(observed.get("raw_value")) != _number(evidence.get("raw_value"))
    ):
        return result("conflicting", "receipt_observation_mismatch", **detail)
    if evidence.get("source_kind") != kind:
        return result("conflicting", "observation_source_kind_mismatch", **detail)
    checks = evidence.get("checks")
    if not isinstance(checks, dict) or any(
        checks.get(key) is not True
        for key in ("identity", "value", "transport", "bytes", "locator")
    ):
        return result("qualified", "observation_checks_incomplete", **detail)
    reconciliation = evidence.get("reconciliation")
    if (
        not isinstance(reconciliation, dict)
        or reconciliation.get("status") != "matched"
    ):
        return result(
            "conflicting"
            if isinstance(reconciliation, dict)
            and reconciliation.get("status") == "conflicting"
            else "qualified",
            "reconciliation_not_matched",
            **detail,
        )
    if evidence.get("unit") != identity.unit or _number(
        evidence.get("value")
    ) != _number(value):
        return result("conflicting", "normalized_value_mismatch", **detail)
    transform = evidence.get("transformation")
    raw = _number(evidence.get("raw_value"))
    if not isinstance(transform, dict) or raw is None or not evidence.get("raw_unit"):
        return result("qualified", "transformation_missing", **detail)
    operation = transform.get("operation")
    factor = _number(transform.get("factor"))
    if operation == "currency_conversion":
        return result("qualified", "independent_fx_operand_not_checked", **detail)
    if operation == "identity":
        if evidence["raw_unit"] != identity.unit or factor not in (None, Decimal(1)):
            return result("conflicting", "identity_unit_mismatch", **detail)
        normalized = raw
    elif operation in ("multiply", "divide") and factor is not None and factor > 0:
        scales = {
            "KES": Decimal(1),
            "million_KES": Decimal(1000000),
            "KES_millions": Decimal(1000000),
            "million_kes": Decimal(1000000),
            "millions_kes": Decimal(1000000),
            "billion_KES": Decimal(1000000000),
            "billion_kes": Decimal(1000000000),
            "billions_kes": Decimal(1000000000),
            "percent": Decimal("0.01"),
            "coefficient": Decimal(1),
        }
        raw_unit = evidence["raw_unit"]
        if raw_unit == identity.unit:
            expected = Decimal(1)
        elif (
            raw_unit not in scales
            or identity.unit not in scales
            or (raw_unit in ("percent", "coefficient"))
            != (identity.unit in ("percent", "coefficient"))
        ):
            return result(
                "qualified", "independent_conversion_operand_not_checked", **detail
            )
        else:
            expected = scales[raw_unit] / scales[identity.unit]
        expected_factor = expected if operation == "multiply" else Decimal(1) / expected
        if factor != expected_factor:
            return result("conflicting", "conversion_factor_mismatch", **detail)
        normalized = raw * expected
    else:
        return result("qualified", "unsupported_transformation", **detail)
    rounding = transform.get("rounding")
    if rounding is not None:
        if type(rounding) is not int or not 0 <= rounding <= 9:
            return result("qualified", "invalid_rounding", **detail)
        modes = {"ROUND_HALF_UP": ROUND_HALF_UP, "ROUND_HALF_EVEN": ROUND_HALF_EVEN}
        mode = transform.get("rounding_mode", "ROUND_HALF_UP")
        if mode not in modes:
            return result("qualified", "unsupported_rounding_mode", **detail)
        if observed.get("transformation") != transform:
            return result(
                "qualified", "rounding_transformation_not_source_bound", **detail
            )
        try:
            normalized = normalized.quantize(
                Decimal(1).scaleb(-rounding), rounding=modes[mode]
            )
        except InvalidOperation:
            return result("qualified", "invalid_transformation_precision", **detail)
    if normalized != _number(value):
        return result("conflicting", "raw_value_transformation_mismatch", **detail)
    try:
        EvidenceReceipt.model_validate(receipt)
        ObservationEvidence.model_validate(evidence)
        from datetime import datetime

        acquired = datetime.fromisoformat(receipt["acquired_at"])
        checked = datetime.fromisoformat(byte_check["checked_at"])
        if acquired.tzinfo is None or checked.tzinfo is None or checked < acquired:
            return result("qualified", "receipt_check_time_invalid", **detail)
    except (ValidationError, ValueError, TypeError):
        return result("qualified", "invalid_receipt_schema", **detail)
    return result(
        "verified",
        "retained_source_and_observation_matched",
        locator=locator,
        document_bytes_checked=True,
        value_checked=True,
        **detail,
    )


def _evidence_entries(row):
    containers = []
    meta = getattr(row, "meta", None)
    if isinstance(meta, dict):
        containers.append(meta)
    prov = getattr(row, "provenance", None)
    containers.extend(
        prov if isinstance(prov, list) else [prov] if isinstance(prov, dict) else []
    )
    evidence = []
    for container in containers:
        if isinstance(container, dict):
            items = container.get("source_evidence")
            if isinstance(items, list):
                evidence.extend(items)
            elif items is not None:
                evidence.append(items)  # malformed evidence is an explicit limit
    return evidence


def explicit_origin(row, source=None):
    basis = _enum(getattr(row, "basis", None))
    if basis in ("modelled", "projected"):
        return basis
    containers = [getattr(row, "meta", None), getattr(source, "meta", None)]
    prov = getattr(row, "provenance", None)
    containers.extend(prov if isinstance(prov, list) else [prov])
    for container in containers:
        if isinstance(container, dict):
            if container.get("origin") in (
                "app_model",
                "modelled",
                "modeled",
                "projected",
                "projection",
            ):
                return container["origin"]
            if container.get("source_classification") in (
                "test_fixture",
                "modelled_estimate",
            ):
                return "modelled"
    # Existing supported bootstrap identity, not a numerical pattern.
    if getattr(row, "__tablename__", None) == "loans":
        from services.publication_gate import loan_is_modelled_fixture

        if loan_is_modelled_fixture(row):
            return "modelled"
    return None


def row_identities(table, row, entities=None, periods=None):
    entities, periods = entities or {}, periods or {}
    entity_id = getattr(row, "entity_id", None)
    entity = entities.get(entity_id)
    geography = (
        "KEN"
        if entity_id is None or _enum(getattr(entity, "type", None)) == "national"
        else getattr(entity, "canonical_name", None) or f"entity:{entity_id}"
    )
    meta = row.meta if isinstance(getattr(row, "meta", None), dict) else {}
    basis = _enum(getattr(row, "basis", None)) or (
        "official_estimate"
        if meta.get("observation_basis") == "official_estimate"
        else "actual"
    )
    dimensions = {}
    if table == "budget_lines":
        period = str(
            getattr(periods.get(row.period_id), "label", f"period:{row.period_id}")
        )
        measures = {
            name: row.currency
            for name in ("allocated_amount", "actual_spent", "committed_amount")
        }
        dimensions = {
            key: getattr(row, key, None)
            for key in ("category", "subcategory", "line_type")
        }
    elif table == "loans":
        observed_dates = []
        prov = row.provenance if isinstance(row.provenance, list) else [row.provenance]
        for entry in prov:
            if isinstance(entry, dict):
                observed_dates.extend(
                    entry[key]
                    for key in ("as_at", "as_of", "measurement_date")
                    if key in entry
                )
        from datetime import date

        month_periods = [
            entry["measurement_period"]
            for entry in prov
            if isinstance(entry, dict) and "measurement_period" in entry
        ]
        try:
            if month_periods:
                import re

                if any(
                    not isinstance(day, str)
                    or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", day)
                    for day in month_periods
                ):
                    raise ValueError("Invalid month period")
                dates = set(month_periods)
            else:
                dates = {date.fromisoformat(day).isoformat() for day in observed_dates}
            period = (
                next(iter(dates))
                if len(dates) == 1
                else "conflicting_reporting_dates"
                if dates
                else "unreported_reporting_date"
            )
        except (TypeError, ValueError):
            period = "invalid_reporting_date"
        measures = {
            "outstanding": row.currency,
            "principal": row.currency,
            "interest_rate": "percent",
        }
        dimensions = {"lender": row.lender, "debt_category": _enum(row.debt_category)}
    elif table == "gdp_data":
        period = str(row.year) + (f"-{row.quarter}" if row.quarter else "")
        measures = {"gdp_value": row.currency, "gdp_growth_rate": "percent"}
        basis = (
            basis
            if basis in ("modelled", "projected")
            else meta.get("price_basis", "current_prices")
        )
    elif table == "economic_indicators":
        period = (
            row.indicator_date.strftime("%Y")
            if meta.get("frequency") == "annual"
            or row.indicator_type
            in (
                "inflation_rate",
                "inflation_rate_annual",
                "inflation_annual_average",
                "gdp_growth_rate",
                "unemployment_rate",
                "total_national_gdp",
            )
            else row.indicator_date.strftime("%Y-%m")
        )
        measures = {row.indicator_type: row.unit or "undeclared"}
        if row.indicator_type.lower() == "cpi":
            dimensions = {"base_period": meta.get("base_period")}
    elif table == "poverty_indices":
        period = str(row.year)
        measures = {
            "poverty_headcount_rate": "percent",
            "extreme_poverty_rate": "percent",
            "gini_coefficient": "coefficient",
        }
    elif table == "debt_timeline":
        period = str(row.year)
        measures = {name: row.unit for name in ("external", "domestic", "total", "gdp")}
    elif table == "revenue_by_source":
        period = row.fiscal_year
        measures = {
            "amount_billion_kes": "billion_KES",
            "share_of_total_pct": "percent",
        }
        dimensions = {"revenue_type": row.revenue_type, "category": row.category}
    else:
        raise ValueError(f"Unsupported qualification table: {table}")
    return {
        name: ObservationIdentity(
            measure=name,
            entity_id=entity_id,
            geography=geography,
            period=period,
            unit=unit,
            basis="current_prices"
            if table == "debt_timeline" and name == "gdp"
            else basis,
            dimensions=dimensions,
        )
        for name, unit in measures.items()
    }


def qualify_rows(db, table, rows):
    """Bounded context loads, independent of row count (at most five queries).

    Budget context uses plain projections so unrelated model columns cannot be
    loaded lazily. Source metadata and the complete response receipt remain
    intact; other tables retain their full publication-check context.
    """
    from models import Country, Entity, Extraction, FiscalPeriod, SourceDocument

    rows = list(rows)
    budget = table == "budget_lines"
    entries = {r.id: _evidence_entries(r) for r in rows}
    ids = {r.source_document_id for r in rows if r.source_document_id is not None}
    for items in entries.values():
        for item in items:
            ref = item.get("receipt") if isinstance(item, dict) else None
            if isinstance(ref, dict) and type(ref.get("source_document_id")) is int:
                ids.add(ref["source_document_id"])
    docs = (
        {
            d.id: d
            for d in db.query(
                *(
                    (
                        SourceDocument.id, SourceDocument.country_id,
                        SourceDocument.publisher, SourceDocument.url,
                        SourceDocument.content_type, SourceDocument.meta,
                    )
                    if budget
                    else (SourceDocument,)
                )
            ).filter(SourceDocument.id.in_(ids)).all()
        }
        if ids
        else {}
    )
    entity_ids = {getattr(r, "entity_id", None) for r in rows} - {None}
    entities = (
        {
            e.id: e
            for e in db.query(
                *(
                    (Entity.id, Entity.country_id, Entity.type, Entity.canonical_name)
                    if budget
                    else (Entity,)
                )
            ).filter(Entity.id.in_(entity_ids)).all()
        }
        if entity_ids
        else {}
    )
    period_ids = {r.period_id for r in rows} if table == "budget_lines" else set()
    periods = (
        {
            p.id: p
            for p in db.query(FiscalPeriod.id, FiscalPeriod.label)
            .filter(FiscalPeriod.id.in_(period_ids))
            .all()
        }
        if period_ids
        else {}
    )
    country_ids = {d.country_id for d in docs.values()} | {
        e.country_id for e in entities.values()
    }
    countries = (
        {
            c.id: c
            for c in db.query(
                *((Country.id, Country.iso_code) if budget else (Country,))
            ).filter(Country.id.in_(country_ids)).all()
        }
        if country_ids
        else {}
    )
    receipt_ids = {
        r.extraction_id
        for r in rows
        if table == "economic_indicators"
        and r.indicator_type.lower() == "cpi"
        and r.extraction_id is not None
    }
    for items in entries.values():
        for item in items:
            ref = item.get("receipt") if isinstance(item, dict) else None
            if isinstance(ref, dict) and type(ref.get("extraction_id")) is int:
                receipt_ids.add(ref["extraction_id"])
    receipts = (
        {
            r.id: r
            for r in db.query(
                *(
                    (
                        Extraction.id, Extraction.source_document_id,
                        Extraction.extractor,
                        Extraction.extracted_json["response_receipt"].label("response_receipt"),
                    )
                    if budget
                    else (Extraction,)
                )
            ).filter(Extraction.id.in_(receipt_ids)).all()
        }
        if receipt_ids
        else {}
    )
    output = {}
    for row in rows:
        doc = docs.get(row.source_document_id)
        identities = row_identities(table, row, entities, periods)
        qualifications = {}
        for measure, identity in identities.items():
            matching = [
                e
                for e in entries[row.id]
                if isinstance(e, dict)
                and isinstance(e.get("identity"), dict)
                and e["identity"].get("measure") == measure
            ]
            malformed = [
                e
                for e in entries[row.id]
                if not isinstance(e, dict) or not isinstance(e.get("identity"), dict)
            ]
            evidence = (
                matching[0]
                if len(matching) == 1
                else malformed[0]
                if malformed
                else None
            )
            ref = evidence.get("receipt", {}) if isinstance(evidence, dict) else {}
            extraction = (
                receipts.get(ref.get("extraction_id"))
                if isinstance(ref, dict)
                else None
            )
            receipt = None
            if extraction is not None and extraction.extractor in (
                "http-response-v1", "pdf-receipt-v1"
            ):
                if budget:
                    # A named JSON member on a non-object root is NULL in the
                    # supported PostgreSQL/SQLite dialects, preserving refusal
                    # of serialized strings, arrays and malformed payloads.
                    receipt = extraction.response_receipt
                elif isinstance(extraction.extracted_json, dict):
                    receipt = extraction.extracted_json.get("response_receipt")
            evidence_source_id = (
                ref.get("source_document_id", row.source_document_id)
                if isinstance(ref, dict)
                else row.source_document_id
            )
            evidence_doc = docs.get(evidence_source_id)
            refusal = None
            if len(matching) > 1:
                refusal = "multiple_observation_evidence"
            elif (
                extraction is not None
                and extraction.source_document_id != evidence_source_id
            ):
                refusal = "receipt_source_document_mismatch"
            country = countries.get(getattr(evidence_doc, "country_id", None))
            entity = entities.get(getattr(row, "entity_id", None))
            if evidence_doc is not None and (
                country is None
                or country.iso_code != "KEN"
                or entity is not None
                and entity.country_id != evidence_doc.country_id
            ):
                refusal = "source_country_mismatch"
            if table == "loans" and identity.period in (
                "conflicting_reporting_dates",
                "invalid_reporting_date",
            ):
                refusal = identity.period
            if table == "economic_indicators":
                from services.publication_gate import economic_publication_failure

                class StoredContext:
                    def get(self, model, key):
                        return {
                            SourceDocument: docs,
                            Country: countries,
                            Extraction: receipts,
                        }[model].get(key)

                refusal = economic_publication_failure(row, StoredContext()) or refusal
            value = (
                row.value
                if table == "economic_indicators"
                else getattr(row, measure, None)
            )
            if table == "revenue_by_source":
                from services.revenue_publication import revenue_source_row

                public = revenue_source_row(row)
                if measure == "share_of_total_pct":
                    value = None
                elif public["absent_reason"]:
                    refusal = public["absent_reason"]
                    value = None
            q = evaluate_qualification(
                identity,
                value,
                source=evidence_doc,
                evidence=evidence,
                receipt=receipt,
                origin=explicit_origin(row, doc),
                refusal=refusal,
            )
            if (
                table == "loans"
                and identity.period == "unreported_reporting_date"
                and q.status == "verified"
            ):
                q = q.model_copy(
                    update={
                        "status": "qualified",
                        "reason": "loan_observation_date_missing",
                        "value_checked": False,
                        "document_bytes_checked": False,
                    }
                )
            qualifications[measure] = q.model_dump(mode="json")
        if table == "debt_timeline":
            qualifications["gdp_ratio"] = qualify_ratio(
                qualifications["total"],
                qualifications["gdp"],
                row.gdp_ratio,
                row.total,
                row.gdp,
            )
        output[row.id] = qualifications
    return output


def qualify_ratio(
    numerator,
    denominator,
    value,
    numerator_value,
    denominator_value,
    *,
    measure="gdp_ratio",
    rounding=1,
):
    """Ratios need independently checked operands; amount evidence is insufficient."""
    identity = ObservationIdentity.model_validate(
        {
            **numerator["identity"],
            "measure": measure,
            "unit": "percent",
            "basis": "derived",
        }
    )
    fields = dict(
        identity=identity, source_document_id=numerator.get("source_document_id")
    )
    if value is None:
        return FigureQualification(
            status="unavailable", reason="value_not_reported", **fields
        ).model_dump(mode="json")
    n, d, ratio = _number(numerator_value), _number(denominator_value), _number(value)
    if type(rounding) is not int or not 0 <= rounding <= 9:
        return FigureQualification(
            status="unavailable", reason="invalid_ratio_precision", **fields
        ).model_dump(mode="json")
    computed = None
    if n is not None and d is not None and d > 0:
        try:
            computed = (n / d * 100).quantize(
                Decimal(1).scaleb(-rounding), rounding=ROUND_HALF_UP
            )
        except InvalidOperation:
            return FigureQualification(
                status="unavailable", reason="invalid_ratio_precision", **fields
            ).model_dump(mode="json")
    if n is None or d is None or d <= 0 or ratio is None:
        status, reason = "unavailable", "invalid_ratio_operands"
    elif computed != ratio:
        status, reason = "conflicting", "ratio_arithmetic_mismatch"
    elif any(
        numerator["identity"][key] != denominator["identity"][key]
        for key in ("entity_id", "geography", "period", "unit")
    ):
        status, reason = "conflicting", "ratio_operand_identity_mismatch"
    elif "projected" in (numerator["status"], denominator["status"]):
        status, reason = "projected", "ratio_projected_operand"
    elif "modelled" in (numerator["status"], denominator["status"]):
        status, reason = "modelled", "ratio_modelled_operand"
    elif all(
        q["status"] == "verified"
        and q.get("value_checked") is True
        and q.get("document_bytes_checked") is True
        and q.get("receipt_id") is not None
        and q.get("digest")
        for q in (numerator, denominator)
    ):
        status, reason = "verified", "independently_matched_ratio_operands"
    elif "conflicting" in (numerator["status"], denominator["status"]):
        status, reason = "conflicting", "ratio_operand_conflicting"
    else:
        status, reason = "qualified", "ratio_operands_not_independently_checked"
    return FigureQualification(
        status=status,
        reason=reason,
        value_checked=status == "verified",
        document_bytes_checked=status == "verified",
        **fields,
    ).model_dump(mode="json")
