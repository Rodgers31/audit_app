#!/bin/bash
# Demonstrate source-access observations, not financial ingestion.
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${PYTHON:-python3}"
results_file="${1:-etl_test_results.json}"

"$python_bin" "$script_dir/etl_test_runner.py" --output "$results_file"
"$python_bin" - "$results_file" <<'PY'
import json
import sys

with open(sys.argv[1]) as f:
    results = json.load(f)
print(f"Sources checked: {results['sources_tested']}")
print(f"Sources accessible: {results['sources_accessible']}")
print(f"Source check errors: {results['errors_encountered']}")
print("Financial data: not extracted")
for source in results['detailed_results']['sources_checked']:
    print(f"{source['source']}: accessible={source['accessible']}")
    if source.get('accessible'):
        print(f"  Page: {source['page_title']}")
        for link in source.get('sample_pdfs', []):
            print(f"  Discovered link (not downloaded): {link}")
PY
