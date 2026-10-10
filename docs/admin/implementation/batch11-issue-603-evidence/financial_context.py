"""Read-only source comparison for the dated four-site financial review."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

BASE = "bcb5ff99854de595bbe3f7d60cc8796b7ada5a20"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root / "backend"))
    sys.path.insert(0, str(root / "backend/tests"))
    from test_apis_no_invented_national_figures import find_invented_figures, _context_ast_dump
    old = subprocess.check_output(["git", "-C", str(root), "show", BASE + ":backend/main.py"], text=True)
    new = (root / "backend/main.py").read_text()
    def definitions(source):
        return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(source).body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    previous, current = definitions(old), definitions(new)
    changed = sorted(n for n in set(previous) | set(current) if previous.get(n) != current.get(n))
    previous_sites = [f.split(": ", 1)[1] for f in find_invented_figures(old, "backend/main.py")]
    sites = [f.split(": ", 1)[1] for f in find_invented_figures(new, "backend/main.py")]
    if changed != ["_startup_sequence"] or sites != previous_sites or len(sites) != 4:
        raise RuntimeError("Review premise changed; full additional context review required")
    print(json.dumps(dict(generated_by="docs/admin/implementation/batch11-issue-603-evidence/financial_context.py",
        generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        base=BASE, old_source_sha256=hashlib.sha256(old.encode()).hexdigest(),
        current_source_sha256=hashlib.sha256(new.encode()).hexdigest(),
        old_ast_sha256=hashlib.sha256(_context_ast_dump(ast.parse(old)).encode()).hexdigest(), current_ast_sha256=hashlib.sha256(_context_ast_dump(ast.parse(new)).encode()).hexdigest(),
        old_raw_sites=previous_sites, current_raw_sites=sites, changed_functions=changed,
        unchanged_financial_definitions={n: hashlib.sha256(current[n].encode()).hexdigest() for n in (
            "county_financial_health", "get_counties", "get_county_details", "get_county_comprehensive",
            "_response_meta", "get_budget_overview", "get_fiscal_summary", "_latest_imf_debt_to_gdp",
            "get_national_debt", "get_debt_sustainability", "get_debt_broader", "_published_debt_projections")}), indent=2))


if __name__ == "__main__":
    main()
