"""
ETL Smoke Test — checks government site reachability and page structure.

Run:  python -m etl.smoke_test
Exit code 0 = all sites OK, 1 = some sites degraded, 2 = critical failure.

Checks:
  1. HTTP reachability (status ≤ 499)
  2. PDF link presence (at least one .pdf link on page)
  3. Key structural marker (element or text expected on page)
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── Sites to probe ──────────────────────────────────────────────────────

TARGETS = [
    {
        "name": "Treasury – QEBR (new Drupal site)",
        "url": "https://newsite.treasury.go.ke/quarterly-economic-and-budgetary-review-report",
        "critical": True,
        "expect_pdf_links": True,
        "expect_text": "QEBR",
    },
    {
        "name": "Treasury – Budget Books (new Drupal site)",
        "url": "https://newsite.treasury.go.ke/budget-books",
        "critical": False,
        "expect_pdf_links": True,
        "expect_text": "budget",
    },
    {
        "name": "Treasury – Budget Policy Statement",
        "url": "https://newsite.treasury.go.ke/budget-policy-statement",
        "critical": False,
        "expect_pdf_links": True,
        "expect_text": "budget",
    },
    {
        "name": "COB – County Reports",
        "url": "https://cob.go.ke/publications/consolidated-county-budget-implementation-review-reports/",
        "critical": True,
        "expect_pdf_links": True,
        "expect_text": "county",
    },
    {
        "name": "COB – WP REST API",
        "url": "https://cob.go.ke/wp-json/wp/v2/media?per_page=5&mime_type=application/pdf",
        "critical": True,
        "expect_pdf_links": False,  # JSON response
        "expect_text": "source_url",
    },
    {
        "name": "OAG – County Audit Reports",
        "url": "https://www.oagkenya.go.ke/county-governments-reports/",
        "critical": True,
        "expect_pdf_links": False,  # JS-rendered DataTables — PDFs not in HTML
        "expect_text": "report",
    },
    {
        "name": "OAG – WP REST API (primary PDF source)",
        "url": "https://www.oagkenya.go.ke/wp-json/wp/v2/media?per_page=5&mime_type=application/pdf&search=audit",
        "critical": True,
        "expect_pdf_links": False,  # JSON response
        "expect_text": "source_url",
    },
    {
        "name": "OAG – National Audit Reports",
        "url": "https://www.oagkenya.go.ke/national-government-audit-reports/",
        "critical": False,
        "expect_pdf_links": False,  # JS-rendered DataTables
        "expect_text": "report",
    },
    {
        "name": "CBK – Public Debt",
        "url": "https://www.centralbank.go.ke/public-debt/",
        "critical": True,
        "expect_pdf_links": False,
        "expect_text": "debt",
    },
    {
        "name": "KNBS – Home",
        "url": "https://www.knbs.or.ke/",
        "critical": False,
        "expect_pdf_links": False,
        "expect_text": "statistics",
    },
]


@dataclass
class ProbeResult:
    name: str
    url: str
    critical: bool
    reachable: bool = False
    status_code: int = 0
    has_pdf_links: Optional[bool] = None
    has_expected_text: bool = False
    response_time_ms: int = 0
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=2, backoff_factor=1, status_forcelist=[502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    return s


def probe(target: dict, session: requests.Session) -> ProbeResult:
    result = ProbeResult(
        name=target["name"],
        url=target["url"],
        critical=target["critical"],
    )
    try:
        t0 = time.monotonic()
        resp = session.get(target["url"], timeout=30, verify=False)
        result.response_time_ms = int((time.monotonic() - t0) * 1000)
        result.status_code = resp.status_code
        result.reachable = resp.status_code < 500

        if not result.reachable:
            result.error = f"HTTP {resp.status_code}"
            return result

        body = resp.text.lower()

        # Check for expected text
        if target.get("expect_text"):
            result.has_expected_text = target["expect_text"].lower() in body
            if not result.has_expected_text:
                result.warnings.append(
                    f"Expected text '{target['expect_text']}' not found — page may have changed"
                )

        # Check for PDF links
        if target.get("expect_pdf_links"):
            result.has_pdf_links = ".pdf" in body
            if not result.has_pdf_links:
                result.warnings.append(
                    "No .pdf links found on page — scraper may not find documents"
                )

        # Extra checks
        if result.response_time_ms > 15_000:
            result.warnings.append(f"Slow response ({result.response_time_ms}ms)")

    except requests.exceptions.SSLError as e:
        result.error = f"SSL error: {e}"
    except requests.exceptions.ConnectionError as e:
        result.error = f"Connection failed: {e}"
    except requests.exceptions.Timeout:
        result.error = "Timeout (>30s)"
    except Exception as e:
        result.error = str(e)

    return result


def run_smoke_test() -> int:
    """Run all probes and return exit code."""
    session = _session()
    results: List[ProbeResult] = []

    print("=" * 72)
    print("  ETL SMOKE TEST — Government Site Reachability")
    print("=" * 72)
    print()

    for target in TARGETS:
        print(f"  Probing {target['name']}...", end=" ", flush=True)
        r = probe(target, session)
        results.append(r)

        if r.error:
            icon = "FAIL" if r.critical else "WARN"
            print(f"[{icon}] {r.error}")
        elif r.warnings:
            print(
                f"[ OK ] {r.status_code} ({r.response_time_ms}ms) — {'; '.join(r.warnings)}"
            )
        else:
            print(f"[ OK ] {r.status_code} ({r.response_time_ms}ms)")

    print()
    print("-" * 72)

    # Summary
    critical_failures = [
        r for r in results if r.critical and (r.error or not r.reachable)
    ]
    all_warnings = [w for r in results for w in r.warnings]
    degraded = [r for r in results if r.warnings and not r.error]

    if critical_failures:
        print()
        print("  CRITICAL FAILURES:")
        for r in critical_failures:
            print(f"    ✗ {r.name}: {r.error}")
        print()
        print("  The ETL pipeline will NOT be able to scrape these sources.")
        print("  Check if the sites are down, or if URLs have changed.")
        exit_code = 2
    elif all_warnings:
        print()
        print("  WARNINGS (sites reachable but structure may have changed):")
        for r in degraded:
            for w in r.warnings:
                print(f"    ⚠ {r.name}: {w}")
        print()
        print("  The ETL pipeline may scrape fewer documents than expected.")
        print(
            "  Consider updating selectors in etl/sources.yaml or etl/kenya_pipeline.py."
        )
        exit_code = 1
    else:
        print()
        print("  All sites reachable and responding as expected.")
        exit_code = 0

    ok_count = sum(1 for r in results if r.reachable and not r.error)
    print(f"\n  Result: {ok_count}/{len(results)} sites OK")
    print("=" * 72)

    return exit_code


if __name__ == "__main__":
    # Suppress SSL warnings for gov sites with certificate issues
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    sys.exit(run_smoke_test())
