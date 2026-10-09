"""
Historical backfill runner for Treasury, COB, and OAG documents.

Features
- Source selection: TREASURY/COB/OAG (default all)
- Year filtering: BACKFILL_YEAR_FROM/BACKFILL_YEAR_TO (optional)
- Concurrency: BACKFILL_CONCURRENCY (default 3)
- Resume & dedupe: uses KenyaDataPipeline manifest (md5) + optional URL checkpoint
- Rate-limited courteous crawling

Usage
  python -m etl.backfill

Environment variables
  BACKFILL_SOURCES=treasury,cob,oag
  BACKFILL_YEAR_FROM=2014
  BACKFILL_YEAR_TO=2025
  BACKFILL_CONCURRENCY=3
  BACKFILL_STORAGE=etl/downloads (optional)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .kenya_pipeline import KenyaDataPipeline


def _year_from_title(title: str) -> Optional[int]:
    t = (title or "").lower()
    m = re.search(r"(20\d{2})\s*[/–-]\s*(20\d{2})", t)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    m2 = re.search(r"(20\d{2})", t)
    return int(m2.group(1)) if m2 else None


def _filter_by_year(
    docs: Iterable[Dict[str, Any]], yfrom: Optional[int], yto: Optional[int]
):
    if yfrom is None and yto is None:
        for d in docs:
            yield d
        return
    for d in docs:
        y = _year_from_title(d.get("title", ""))
        if y is None:
            # Keep unknown year to avoid missing important docs
            yield d
            continue
        if yfrom is not None and y < yfrom:
            continue
        if yto is not None and y > yto:
            continue
        yield d


async def _bounded_gather(limit: int, coros: Iterable[asyncio.Future]):
    sem = asyncio.Semaphore(limit)

    async def _run(coro):
        async with sem:
            return await coro

    return await asyncio.gather(*(_run(c) for c in coros))


async def run_backfill():
    sources_str = os.getenv("BACKFILL_SOURCES", "treasury,cob,oag")
    sources = [s.strip().lower() for s in sources_str.split(",") if s.strip()]
    yfrom = os.getenv("BACKFILL_YEAR_FROM")
    yto = os.getenv("BACKFILL_YEAR_TO")
    year_from = int(yfrom) if yfrom and yfrom.isdigit() else None
    year_to = int(yto) if yto and yto.isdigit() else None
    concurrency = int(os.getenv("BACKFILL_CONCURRENCY", "3"))
    storage = os.getenv("BACKFILL_STORAGE")

    pipe = KenyaDataPipeline(storage_path=storage)
    pipe.db_loader.check_ownership_ready()

    all_docs: List[Dict[str, Any]] = []
    for sk in sources:
        all_docs.extend(pipe.discover_budget_documents(sk))

    # Filter by year window if configured
    filtered = list(_filter_by_year(all_docs, year_from, year_to))

    # Dedupe by URL
    seen = set()
    queue = []
    for d in filtered:
        u = d.get("url")
        if not u or u in seen:
            continue
        seen.add(u)
        queue.append(d)

    # Process with bounded concurrency
    async def _process_one(doc):
        res = await pipe.download_and_process_document(doc)
        # Be polite between requests; pipeline already delays post-request per doc
        await asyncio.sleep(0.5)
        return bool(res)

    ok_flags = await _bounded_gather(concurrency, (_process_one(d) for d in queue))

    summary = {
        "requested": len(all_docs),
        "filtered": len(filtered),
        "queued_unique": len(queue),
        "succeeded": sum(1 for b in ok_flags if b),
        "failed": sum(1 for b in ok_flags if not b),
        "sources": sources,
        "year_from": year_from,
        "year_to": year_to,
    }

    out = Path(pipe.storage_path) / f"backfill_summary.json"
    out.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    if summary["failed"]:
        raise RuntimeError("Legacy backfill had failed/refused documents; see summary")


if __name__ == "__main__":
    asyncio.run(run_backfill())
