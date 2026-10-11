"""Run CRA parser refusal controls with explicit checks, for ``python -O`` too.

pytest assertion rewriting is not a guarantee under -O, so this control uses
plain ``if`` checks and exits nonzero on any unexpected acceptance. It proves the
product parser never depends on ``assert`` for validation.
"""
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "backend"))
import pdfplumber  # noqa: E402
from seeding.domains.cra import parser, source  # noqa: E402

PDF = ROOT / "docs/admin/implementation/batch11-issue-602-evidence/fixtures/cra-fy2026-27.pdf"
with pdfplumber.open(PDF) as pdf:
    TABLE = pdf.pages[38].extract_tables()[0]


def refuses(call):
    try:
        call()
    except source.CraSourceRefused:
        return True
    return False


def mutated(fn):
    table = copy.deepcopy(TABLE)
    fn(table)
    return table


cases = {
    "header_negation": mutated(lambda t: t[0].__setitem__(13, "Not Recommended")),
    "header_historical": mutated(lambda t: t[0].__setitem__(13, "Previously Recommended")),
    "header_year_prefix": mutated(lambda t: t[3].__setitem__(13, "FY 2026/270")),
    "values_only_swap": mutated(lambda t: [t[5].__setitem__(6, "2,513.76"), t[5].__setitem__(12, "2,215.1")]),
    "oversized": mutated(lambda t: [t[5].__setitem__(12, "9" * 32), t[10].__setitem__(13, "1" + "0" * 32)]),
}
results = {name: refuses(lambda table=table: parser.parse_table(table)) for name, table in cases.items()}
results["amount_bool"] = refuses(lambda: parser.amount(True))
results["amount_32_digits"] = refuses(lambda: parser.amount("9" * 32))
real = parser.parse_publication(PDF.read_bytes())["amounts_kes"]
positive = real == {"national_government": "2513760000000", "county_governments": "458940000000",
                    "equalisation_fund": "9600000000", "total_shareable_revenue": "2982300000000"}
print(json.dumps({"optimize": sys.flags.optimize, "refusals": results, "positive_control": positive}, sort_keys=True))
sys.exit(0 if all(results.values()) and positive else 1)
