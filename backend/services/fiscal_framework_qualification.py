"""Per-cell evidence for one Treasury fiscal-framework column.

The parser issues these proofs only after identifying and reconciling a printed
column. A document locator or one qualified headline cannot certify its peers.
This is a publication contract, not original-acquisition or adoption authority.
"""
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from services.fiscal_outturns import finite_number

# Public key -> printed source row. The locator binds a proof to its own cell,
# including cells whose amounts happen to equal another row (especially zero).
FRAMEWORK_CELLS = {
    "total_expenditure_billion": "Expenditure and Net Lending",
    "recurrent_billion": "Recurrent Expenditure",
    "interest_payments_billion": "Interest Payments",
    "development_billion": "Development and Net Lending",
    "county_transfers_billion": "County Transfers",
    "county_equitable_share_billion": "Equitable Share",
    "contingency_billion": "Contingency",
    "total_revenue_incl_aia_billion": "Total Revenue including A-i-A",
    "ordinary_revenue_billion": "Ordinary Revenue",
    "ministerial_aia_billion": "Ministerial Appropriation in Aid",
    "grants_billion": "Grants",
    "fiscal_deficit_incl_grants_billion": "Fiscal Balance including Grants (sign reversed)",
    "adjustment_to_cash_basis_billion": "Adjustment to Cash Basis",
    "statistical_discrepancy_billion": "Statistical Discrepancy",
    "total_financing_billion": "Total Financing",
    "net_foreign_financing_billion": "Net Foreign Financing",
    "net_domestic_financing_billion": "Net Domestic Financing",
    "nominal_gdp_billion": "Nominal GDP",
    "tax_revenue_billion": "Tax Revenue",
    "non_tax_revenue_billion": "Non-Tax Revenue",
}
TAX_HEADS = {
    "income_tax": "Income Tax", "import_duty": "Import Duty",
    "excise_duty": "Excise Duty", "vat": "Value Added Tax",
    "other_tax": "Other Tax Revenue",
}
SIGNED_FIELDS = frozenset({
    "fiscal_deficit_incl_grants_billion", "total_financing_billion",
    "adjustment_to_cash_basis_billion", "statistical_discrepancy_billion",
    "net_foreign_financing_billion", "net_domestic_financing_billion",
})
CORE_FIELDS = (
    "total_revenue_incl_aia_billion", "total_expenditure_billion",
    "fiscal_deficit_incl_grants_billion", "total_financing_billion",
    "grants_billion", "adjustment_to_cash_basis_billion",
    "statistical_discrepancy_billion",
)
PRECISION_KES = 100_000_000  # The accepted Annex parser reads one-decimal billions.


def _printed_quantum(value):
    try:
        return Decimal(str(value)) % PRECISION_KES == 0
    except InvalidOperation:
        return False


def _basis(field):
    if field in {"ordinary_revenue_billion", "tax_revenue_billion", "non_tax_revenue_billion"} or field.startswith("tax_heads_billion."):
        return "ordinary_revenue_excl_aia"
    return {
        "total_revenue_incl_aia_billion": "revenue_including_aia",
        "ministerial_aia_billion": "ministerial_appropriations_in_aid",
        "nominal_gdp_billion": "nominal_gdp_fiscal_year",
    }.get(field, "treasury_fiscal_framework")


def _cells(framework):
    for field, label in FRAMEWORK_CELLS.items():
        yield field, framework.get(field), label
    heads = framework.get("tax_heads_billion")
    if isinstance(heads, dict):
        for field, label in TAX_HEADS.items():
            yield f"tax_heads_billion.{field}", heads.get(field), label


def bind_framework_evidence(framework):
    """Issue per-cell proofs at the accepted source-parser boundary only."""
    from services.fiscal_qualification import VERSION, measure_evidence
    proofs = {}
    for field, value, label in _cells(framework):
        amount = finite_number(value, nonnegative=field not in SIGNED_FIELDS)
        if amount is None:
            continue
        source = deepcopy(framework["source"])
        source["cell"] = label
        proofs[field] = measure_evidence(
            amount * 1e9, framework["fiscal_year"], _basis(field),
            source.get("column"), framework["precision_kes"], source,
        )
    framework["measure_contract"] = {"version": VERSION, "measures": proofs}
    return framework


def _qualify_cell(framework, field, value, label):
    from services.fiscal_qualification import VERSION, fiscal_year_key, valid_source, VINTAGES, public_measure_proof
    contract = framework.get("measure_contract")
    if not isinstance(contract, dict) or contract.get("version") != VERSION:
        return None, None, "framework_measure_contract_missing_or_unknown"
    proofs = contract.get("measures")
    proof = proofs.get(field) if isinstance(proofs, dict) else None
    if not isinstance(proof, dict) or "vintage" not in proof:
        return None, None, "framework_measure_source_unconfirmed"
    signed = field in SIGNED_FIELDS
    amount = finite_number(value, nonnegative=not signed)
    witnessed = finite_number(proof.get("value_kes"), nonnegative=not signed)
    precision = finite_number(proof.get("precision_kes"))
    source, own_source = framework.get("source"), proof.get("source")
    vintage = proof.get("vintage")
    # Independently witnessed unknown headers stay unknown; never infer a
    # vintage from age. A known header must match the proof exactly.
    column = source.get("column") if isinstance(source, dict) else None
    known_vintage = isinstance(vintage, str) and vintage in VINTAGES
    unknown_vintage = vintage in (None, "Vintage unconfirmed") and column in (None, "", "Vintage unconfirmed")
    if (amount is None or witnessed is None or round(amount * 1e9, 2) != witnessed
            or not _printed_quantum(witnessed)
            or precision != PRECISION_KES or type(framework.get('precision_kes')) not in (int, float)
            or framework['precision_kes'] != PRECISION_KES
            or proof.get("basis") != _basis(field)
            or fiscal_year_key(proof.get("fiscal_year")) != fiscal_year_key(framework.get("fiscal_year"))
            or not (known_vintage and vintage == column or unknown_vintage)
            or not valid_source(own_source) or not valid_source(source)
            or any(own_source.get(k) != source.get(k) for k in ("url", "sha256", "page", "table", "edition", "column"))
            or own_source.get("cell") != label):
        return None, None, "framework_measure_evidence_invalid_or_contradictory"
    return amount, public_measure_proof(proof), None


def validate_framework_contract(framework, fiscal_year):
    """Preflight declared parser proofs before any member of a batch is written.

    Old inputs without a contract remain unqualified; they cannot replace a
    qualified retained framework. A declared contradictory proof is refused.
    """
    from services.fiscal_qualification import VERSION, fiscal_year_key
    if not isinstance(framework, dict) or 'measure_contract' not in framework:
        return
    contract = framework['measure_contract']
    if (not isinstance(contract, dict) or contract.get('version') != VERSION
            or not isinstance(contract.get('measures'), dict)):
        raise ValueError('invalid fiscal framework measure contract')
    cells = {field: (value, label) for field, value, label in _cells(framework)}
    if (fiscal_year_key(fiscal_year) is None
            or fiscal_year_key(framework.get('fiscal_year')) != fiscal_year_key(fiscal_year)
            or not set(CORE_FIELDS).issubset(contract['measures'])):
        raise ValueError('incomplete or incompatible fiscal framework proof')
    for field in contract['measures']:
        if field not in cells or _qualify_cell(framework, field, *cells[field])[2] is not None:
            raise ValueError('invalid fiscal framework cell proof')


def qualified_framework(row):
    """Return a sanitized framework and the reason an entire column is absent."""
    from services.fiscal_qualification import VERSION, fiscal_year_key, valid_source, public_source
    from services.fiscal_outturns import _outturn_from_framework
    meta = row.meta if isinstance(row.meta, dict) else {}
    framework = meta.get("fiscal_framework")
    if (not isinstance(framework, dict) or framework.get("basis") != "treasury_fiscal_framework"
            or fiscal_year_key(row.fiscal_year) is None
            or fiscal_year_key(framework.get("fiscal_year")) != fiscal_year_key(row.fiscal_year)
            or not valid_source(framework.get("source"))):
        return None, "framework_source_or_period_unconfirmed"
    # Allowlist output, so an unknown nested financial field cannot bypass the
    # contract. Raw parser checks contain numbers too and are not public proof.
    result = {key: framework[key] for key in ("basis", "fiscal_year")}
    if isinstance(framework.get('identified_by'), str):
        result['identified_by'] = framework['identified_by']
    result['source'] = public_source(framework['source'])
    result['precision_kes'] = PRECISION_KES
    result['measure_contract_version'] = VERSION
    reasons, proofs = {}, {}
    heads = {}
    for field, value, label in _cells(framework):
        amount, proof, reason = _qualify_cell(framework, field, value, label)
        if field.startswith("tax_heads_billion."):
            heads[field.partition(".")[2]] = amount
        else:
            result[field] = amount
        if reason:
            reasons[field] = reason
        else:
            proofs[field] = proof
    missing = [field for field in CORE_FIELDS if result.get(field) is None]
    if missing:
        return None, "framework_core_measure_unqualified: " + ", ".join(missing)
    if _outturn_from_framework(row, result)["absent_reason"] is not None:
        return None, "framework_totals_do_not_reconcile"
    def withhold(fields, reason):
        for field in fields:
            result[field] = None
            proofs.pop(field, None)
            reasons[field] = reason
    revenue_parts = ("ordinary_revenue_billion", "ministerial_aia_billion")
    if all(result.get(k) is not None for k in revenue_parts):
        if abs(sum(result[k] for k in revenue_parts) - result["total_revenue_incl_aia_billion"]) > .150001:
            return None, "framework_revenue_parts_do_not_reconcile"
    parts = ("recurrent_billion", "development_billion", "county_transfers_billion", "contingency_billion")
    if (any(result.get(k) is None for k in parts)
            or abs(sum(result[k] for k in parts) - result["total_expenditure_billion"]) > .250001):
        withhold((*parts, "interest_payments_billion", "county_equitable_share_billion"), "framework_expenditure_split_unqualified_or_disagrees")
    interest, recurrent = result.get("interest_payments_billion"), result.get("recurrent_billion")
    if interest is None or recurrent is None or interest > recurrent:
        withhold(("interest_payments_billion",), "framework_interest_unqualified_or_exceeds_recurrent")
    share, transfers = result.get("county_equitable_share_billion"), result.get("county_transfers_billion")
    if share is None or transfers is None or share > transfers:
        withhold(("county_equitable_share_billion",), "framework_share_unqualified_or_exceeds_transfers")
    financing_parts = ("net_foreign_financing_billion", "net_domestic_financing_billion")
    if (any(result.get(k) is None for k in financing_parts)
            or abs(sum(result[k] for k in financing_parts) - result["total_financing_billion"]) > .150001):
        withhold(financing_parts, "framework_financing_parts_unqualified_or_disagree")
    tax, non_tax, ordinary = (result.get(k) for k in ("tax_revenue_billion", "non_tax_revenue_billion", "ordinary_revenue_billion"))
    if (meta.get("tax_split_absent_reason") or framework.get("tax_split_absent_reason")
            or any(v is None for v in (tax, non_tax, ordinary)) or abs(tax + non_tax - ordinary) > .150001):
        withhold(("tax_revenue_billion", "non_tax_revenue_billion"), "framework_tax_split_unqualified_or_disagrees")
        heads = {}
    if (len(heads) != len(TAX_HEADS) or any(v is None for v in heads.values())
            or result.get("tax_revenue_billion") is None or abs(sum(heads.values()) - result["tax_revenue_billion"]) > .300001):
        for field in TAX_HEADS:
            key = f"tax_heads_billion.{field}"
            proofs.pop(key, None)
            reasons.setdefault(key, "framework_tax_heads_unqualified_or_disagree")
        result["tax_heads_billion"] = None
    else:
        result["tax_heads_billion"] = heads
    result.update(measure_qualifications=proofs, absent_reasons=reasons)
    if framework.get("tax_split_absent_reason"):
        reason = framework["tax_split_absent_reason"]
        result["tax_split_absent_reason"] = (reason if isinstance(reason, str) and 0 < len(reason.strip()) <= 2000
                                              else "source_declares_tax_split_absent")
    return result, None
