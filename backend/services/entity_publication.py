"""Public Entity.meta contract. Storage JSON is never a public DTO.

Only county identifiers and attributed officeholder names belong here. Budget,
population, audits, projects and economic claims have their own publication
paths. Unknown keys (including future additions) are private by default.
Nested objects are reconstructed, never copied wholesale.
"""

import re
from urllib.parse import urlsplit


def _code(value):
    return value if isinstance(value, str) and re.fullmatch(r"\d{3}", value) else None


def _text(value):
    return value if isinstance(value, str) and value.strip() else None


def public_entity_metadata(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    out = {}
    if code := _code(raw.get("county_code")):
        out["county_code"] = code
    metrics = raw.get("metrics")
    if isinstance(metrics, dict):
        years = {
            year: {"county_code": code}
            for year, fields in metrics.items()
            if isinstance(year, str)
            and re.fullmatch(r"(?:FY)?\d{4}/\d{2,4}", year)
            and isinstance(fields, dict)
            and (code := _code(fields.get("county_code")))
        }
        if years:
            out["metrics"] = years

    for office in ("governor", "deputy_governor"):
        name, provenance = _text(raw.get(office)), raw.get(f"{office}_provenance")
        if not name or not isinstance(provenance, dict):
            continue
        url, source = _text(provenance.get("source_url")), _text(
            provenance.get("source")
        )
        try:
            parts = urlsplit(url or "")
            valid_url = parts.scheme in ("http", "https") and bool(parts.hostname)
        except ValueError:
            valid_url = False
        if not valid_url or not source:
            continue
        public_provenance = {"source": source, "source_url": url}
        for key in ("extractor", "fetched_at"):
            if value := _text(provenance.get(key)):
                public_provenance[key] = value
        document_id = provenance.get("source_document_id")
        if type(document_id) is int and document_id > 0:
            public_provenance["source_document_id"] = document_id
        out[office] = name
        out[f"{office}_provenance"] = public_provenance
    return out
