"""Measure retained fixture receipt bytes locally; never contact a publisher."""
from pathlib import Path
import gzip
import json
import sys
import tempfile

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from seeding.config import SeedingSettings
from seeding.http_client import SeedingHttpClient
from seeding.domains.revenue_by_source.fetcher import _read_release
from seeding.domains.economic_indicators.cbk_inflation import fetch_cbk_inflation
from seeding.observations import worldbank_observations


def measure():
    base = ROOT / "backend/tests/fixtures"
    page = (base / "kra/fy2025_26_annual_page.html").read_bytes()
    shell = (base / "kra/fy2025_26_dashboard_shell.html").read_bytes()
    with gzip.open(base / "kra/fy2025_26_dashboard_bundle.js.gz", "rb") as stream:
        bundle = stream.read()
    cbk = (base / "cbk/inflation_rates_2026-09-26.html").read_bytes()
    gdp = (base / "worldbank_gdp_2022.json").read_bytes()
    url = "https://www.kra.go.ke/annual-revenue-performance-fy-2025-2026"

    def handler(request):
        address = str(request.url)
        body = (page if address == url else cbk if "inflation-rates" in address
                else gdp if "worldbank" in address else bundle if request.url.path.endswith(".js") else shell)
        kind = "application/json" if body == gdp else "application/javascript" if body == bundle else "text/html"
        return httpx.Response(200, content=body, headers={"content-type": kind})

    with tempfile.TemporaryDirectory(prefix="audit-receipt-measure-") as directory:
        settings = SeedingSettings(storage_path=Path(directory), cache_path=Path(directory), http_cache_enabled=False)
        with SeedingHttpClient(settings, client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
            release = _read_release(client, url, None)
            inflation = fetch_cbk_inflation(client)
            response = client.get("https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN")
            parsed = worldbank_observations(response, client, indicator="NY.GDP.MKTP.CN", measure="gdp_value", unit="KES", quantum="1", basis="current_prices")
        manifests = {"kra": release.response_receipt,
                     "cbk": inflation.records[0]["source_evidence"][0]["_response_receipt"],
                     "gdp": parsed.evidence[2022][0]["_response_receipt"]}
        objects = list((Path(directory) / "response-receipts").glob("*/*"))
        return {"scope": "local retained fixture bytes; MockTransport; no publisher/network/provider read",
                "responses": {name: {"body_bytes": item["byte_size"], "digest": item["digest"],
                                     "observations": len(item["observations"]),
                                     "receipt_json_bytes": len(json.dumps(item).encode())}
                              for name, item in manifests.items()},
                "unique_local_objects": len(objects), "unique_local_body_bytes": sum(p.stat().st_size for p in objects)}


if __name__ == "__main__":
    print(json.dumps(measure(), indent=2))
