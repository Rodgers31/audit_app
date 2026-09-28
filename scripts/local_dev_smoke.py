#!/usr/bin/env python3
"""Check the running local fixture API without touching any remote host."""

import json
from urllib.request import urlopen


BASE = "http://127.0.0.1:18080"


def get(path):
    with urlopen(BASE + path, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"{path} returned {response.status}")
        return json.load(response)


def main():
    counties = {item["name"]: item for item in get("/api/v1/counties")}
    # counties-literal-ok: these are the two synthetic rows in the local acceptance fixture.
    assert set(counties) == {"Nairobi", "Mombasa"}
    assert counties["Nairobi"]["total_budget"] == 100_000_000_000
    assert counties["Nairobi"]["audit_status"] == "qualified"
    assert counties["Mombasa"]["total_budget"] is None
    assert counties["Mombasa"]["audit_status"] == "pending"

    detail = get("/api/v1/counties/nairobi")
    older = get("/api/v1/counties/nairobi?fiscal_year=2024/25")
    assert detail["total_budget"] == 100_000_000_000
    assert older["total_budget"] == 50_000_000_000
    assert get("/api/v1/counties/fiscal-years")["default"] == "FY2025/26 9M"

    findings = get("/api/v1/counties/nairobi/audits/list")
    assert findings["total"] == 1
    assert findings["items"][0]["description"].startswith("Synthetic finding:")
    assert get("/api/v1/counties/nairobi/audits/list?year=FY2025/26%209M")["total"] == 0
    fiscal = get("/api/v1/fiscal/summary")
    assert fiscal["status"] == "no_data" and fiscal["current"] is None
    print("Local fixture API passed: counties, detail, fiscal years, audit publication, unavailable data")


if __name__ == "__main__":
    main()
