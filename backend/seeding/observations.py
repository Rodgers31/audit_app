"""Source-byte bound World Bank observations with compact per-measure receipts."""
from __future__ import annotations

import json
from decimal import Decimal, ROUND_HALF_EVEN

from services.response_receipts import capture_response


class ObservedSeries(dict):
    def __init__(self, *args, evidence=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.evidence = evidence or {}


def worldbank_observations(response, client, *, indicator: str, measure: str,
                           unit: str, factor="1", quantum="0.01", basis="actual",
                           maximum=None, raw_unit=None, allow_negative=False, identity_dimensions=None, period_for_year=None, evidence_quantum=None) -> ObservedSeries:
    """Validate the identity in actual bytes, independent of the requested URL.

    Legacy parser helpers remain usable for local fixtures, but only this strict
    response parser emits evidence for response verification.
    """
    receipt = response.extensions.get("response_receipt")
    if not isinstance(receipt, dict) or "digest" not in receipt:
        receipt = capture_response(response, getattr(client, "receipt_store", None))
    if response.status_code != 200 or "json" not in response.headers.get("content-type", "").lower():
        raise ValueError("World Bank response requires complete 200 JSON")
    payload = json.loads(response.content, parse_float=Decimal)
    if not isinstance(payload, list) or len(payload) != 2 or not isinstance(payload[0], dict) or not isinstance(payload[1], list):
        raise ValueError("Unexpected World Bank response")
    meta, rows = payload
    if meta.get("pages") != 1 or meta.get("page") != 1 or meta.get("total") != len(rows):
        raise ValueError("World Bank response is partial or missing completeness metadata")
    receipt = {**receipt, "parser_version": "worldbank-observation-v1"}
    out = ObservedSeries()
    conversion = Decimal(factor)
    precision = Decimal(quantum)
    if not conversion.is_finite() or conversion <= 0 or not precision.is_finite() or precision <= 0:
        raise ValueError("Invalid observation transformation")
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("countryiso3code") != "KEN" or row.get("indicator", {}).get("id") != indicator:
            raise ValueError("World Bank country/indicator mismatch")
        country = row.get("country", {})
        if country.get("id") not in (None, "KE"):
            raise ValueError("World Bank country identity conflict")
        year = row.get("date")
        if not isinstance(year, str) or len(year) != 4 or not year.isdigit() or int(year) < 1:
            raise ValueError("World Bank year mismatch")
        if "value" not in row:
            raise ValueError("Missing World Bank value")
        raw = row["value"]
        if raw is None:
            continue
        if isinstance(raw, bool) or not isinstance(raw, (int, Decimal)):
            raise ValueError("Non-numeric World Bank observation")
        raw = Decimal(raw)
        if not raw.is_finite() or (raw < 0 and not allow_negative) or (maximum is not None and raw > Decimal(maximum)):
            raise ValueError("World Bank observation outside measure bounds")
        if int(year) in out:
            raise ValueError("Duplicate World Bank observation year")
        # This API's unit member is commonly empty. The documented indicator
        # definition supplies the unit; a contradictory nonempty unit refuses.
        source_unit = raw_unit or ("KES" if indicator.endswith(".CN") else "percent")
        declared = row.get("unit")
        if declared not in (None, "", source_unit, "LCU" if source_unit == "KES" else "%"):
            raise ValueError("World Bank unit mismatch")
        value = (raw * conversion).quantize(precision, rounding=ROUND_HALF_EVEN)
        out[int(year)] = value
        matched = receipt["byte_check"]["status"] == "matched"
        out.evidence[int(year)] = [{
            "version": 1, "source_kind": "api",
            "identity": {"measure": measure, "entity_id": None, "geography": "KEN", "period": period_for_year(int(year)) if period_for_year else year,
                         "unit": unit, "basis": basis, "dimensions": identity_dimensions or {}},
            "receipt": {"digest": receipt["digest"]}, "_response_receipt": receipt,
            "raw_value": str(raw), "raw_unit": source_unit, "value": str((raw * conversion).quantize(Decimal(evidence_quantum or quantum), rounding=ROUND_HALF_EVEN)), "unit": unit,
            "parser_version": "worldbank-observation-v1",
            "locator": {"json_path": f"$[1][{index}].value", "indicator": indicator, "country": "KEN", "date": year},
            "transformation": {"operation": "identity" if source_unit == unit and conversion == 1 else "multiply", "factor": factor, "rounding": -Decimal(evidence_quantum or quantum).as_tuple().exponent, "rounding_mode": "ROUND_HALF_EVEN"},
            "checks": {"identity": True, "value": True, "transport": receipt.get("acquired_at") is not None, "bytes": matched, "locator": True},
            "reconciliation": {"status": "matched", "reason": "source_byte_observation_matched; no independent publisher reconciliation"},
        }]
    receipt["observations"] = [
        {key: e[key] for key in ("identity", "locator", "raw_value", "raw_unit", "transformation")}
        for entries in out.evidence.values() for e in entries
    ]
    return out
