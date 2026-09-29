"""Read-only, source-locked reconciliation for OAG county prior-year lists.

The input snapshot is a bounded public /audit/findings read. This tool refuses
to emit a repair manifest if the PDF bytes, the original parser output, or the
observed stored text differ from the reviewed evidence. It never writes a DB.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from seeding.extractors import oag_blue_book as current  # noqa: E402
from seeding.extractors import oag_county_volume as county  # noqa: E402
from seeding.extractors.oag_blue_book import PageText  # noqa: E402


BASE = "c76ad74877dcd29a284b548c928f59538553fa0f"
SOURCE_SHA256 = "aa72b0a512fe01ce8f40b9ed8597bd78657a9f441a8daf4963b07e661104d896"
SNAPSHOT_SHA256 = "a732fe184e84a668c3035004920529e9275e55f0648a7925b81c81b9b7871365"
SOURCE_URL = (
    "https://www.oagkenya.go.ke/wp-content/uploads/2026/05/"
    "AUDITOR-GENERALS-REPORT-ON-COUNTY-GOVERNMENTS-COUNTY-ASSEMBLIES-2024-2025-1.pdf"
)
# Only these source paragraphs changed in a full 47-chapter walk of these bytes.
# IDs and old hashes were observed in bounded public API reads on 2026-09-29.
EXPECTED = {
    (33, 453): (5545, 168, "1e790d1579270439ce49cbb4572915f31c4d0c6efec4e14aa8d1fe2f6d369d85"),
    (44, 603): (5679, 221, "60c5a322498e2a799bbfaf8534e9afa5d64fd8e6672041288bb48b1bde8a2bb4"),
    (47, 645): (5716, 239, "2cac98980ea69e1b0e75dca77e8f190ea190f5c22f719e416365c9dd6e73fdcc"),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def legacy_parser():
    source = subprocess.check_output(
        ["git", "show", f"{BASE}:backend/seeding/extractors/oag_blue_book.py"],
        cwd=ROOT,
    )
    module = types.ModuleType("oag_blue_book_reviewed_baseline")
    sys.modules[module.__name__] = module
    exec(compile(source, f"{BASE}:oag_blue_book.py", "exec"), module.__dict__)
    return module


def walk(pages, split, parser):
    walked = list(pages)
    for ch in split.chapters:
        page = walked[ch.start_page - 1]
        body = page.text.split("\n")
        first = next(i for i, line in enumerate(body) if line.strip())
        walked[ch.start_page - 1] = PageText(
            page.page_number, "\n".join(body[first + 1 :]), page.method
        )

    out = {}
    for ch in split.chapters:
        found, rejected = parser.segment_chapter(
            walked, ch.no, ch.toc_name, ch.start_page, ch.end_page, 0,
            finding_start_re=county.FINDING_START_RE,
            stop_at_appendix=False,
            max_number_step=county.MAX_NUMBER_STEP,
            skip_prior_issue_tables=True,
        )
        if rejected:
            raise ValueError(f"chapter {ch.no}: {rejected} unreadable finding(s)")
        for finding in found:
            key = (ch.no, finding.paragraph_no)
            if key in out:
                raise ValueError(f"duplicate finding key {key}")
            out[key] = finding
    return out


def make_manifest(pdf: Path, snapshot: Path) -> dict:
    snapshot_bytes = snapshot.read_bytes()
    if sha256(snapshot_bytes) != SNAPSHOT_SHA256:
        raise ValueError("public before-snapshot SHA256 differs from reviewed observation")
    actual_sha = sha256(pdf.read_bytes())
    if actual_sha != SOURCE_SHA256:
        raise ValueError(f"source SHA256 mismatch: {actual_sha}")

    pages = current.read_pages(pdf, ocr_enabled=False, visible_only=True)
    fixture = (ROOT / "backend/tests/fixtures/oag_nairobi_assembly_2024_2025_p239_242.txt")
    if fixture.read_text(encoding="utf-8").split("\f") != [
        pages[page - 1].text for page in range(239, 243)
    ]:
        raise ValueError("source-shaped regression fixture differs from reviewed PDF pages")
    split = county.split_volume(pages)
    if len(split.chapters) != 47 or split.refused:
        raise ValueError(f"chapter coverage changed: {len(split.chapters)}, {split.refused}")
    # Only front matter can be unreadable in the reviewed source extraction.
    if [p.page_number for p in pages if p.method == "rejected"] != [1, 9]:
        raise ValueError("source page readability changed")

    old = walk(pages, split, legacy_parser())
    new = walk(pages, split, current)
    if len(old) != 582 or len(new) != 582:
        raise ValueError(f"finding coverage changed: {len(old)} before, {len(new)} after")
    if set(old) != set(new):
        raise ValueError("finding identities changed beyond reviewed text boundaries")
    for key in old:
        before_meta = {k: v for k, v in vars(old[key]).items() if k != "finding_text"}
        after_meta = {k: v for k, v in vars(new[key]).items() if k != "finding_text"}
        if before_meta != after_meta:
            raise ValueError(f"finding metadata changed outside reviewed text: {key}")
    changed = {key for key in old if old[key].finding_text != new[key].finding_text}
    if changed != set(EXPECTED):
        raise ValueError(f"changed source scope is not reviewed: {sorted(changed)}")

    observed = json.loads(snapshot_bytes)
    items = observed.get("items")
    if not isinstance(items, list) or len(items) != len(EXPECTED):
        raise ValueError("public snapshot must contain exactly the three reviewed rows")
    by_id = {row.get("id"): row for row in items}
    if len(by_id) != len(EXPECTED):
        raise ValueError("duplicate public row id")

    rows = []
    for key in sorted(EXPECTED):
        row_id, page, expected_old_hash = EXPECTED[key]
        row = by_id.get(row_id)
        before, after = old[key], new[key]
        reference = f"OAG-CV-2024/2025-A{key[0]}-P{key[1]}"
        footer = pages[page - 1].text.splitlines()[-1].strip()
        if not footer.isdigit():
            raise ValueError(f"source page {page} has no printed-page footer")
        if row is None or any((
            row.get("external_reference") != reference,
            row.get("page_ref") != f"p.{page}",
            row.get("source_document_url") != f"{SOURCE_URL}#page={page}",
            row.get("audited_entity_name") != after.entity_name,
            row.get("audit_year") != 2025,
            row.get("period_id") != 1,
            before.pdf_page != page,
            after.pdf_page != page,
            before.entity_name != after.entity_name,
            before.paragraph_no != after.paragraph_no,
            before.finding_text != row.get("finding_text"),
            sha256(before.finding_text.encode("utf-8")) != expected_old_hash,
            not before.finding_text.startswith(after.finding_text + " List of Unresolved Prior Year"),
        )):
            raise ValueError(f"public/source baseline differs for {reference}; refuse replacement")
        rows.append({
            "id": row_id,
            "external_reference": reference,
            "entity_id": row.get("entity_id"),
            "audited_entity_name": after.entity_name,
            "audit_year": row["audit_year"],
            "period_id": row["period_id"],
            "page_ref": row["page_ref"],
            "source_document_url": row["source_document_url"],
            "source_pdf_page": page,
            "source_printed_page": int(footer),
            "preserved_fields": {
                field: row[field] for field in (
                    "county_name", "severity", "query_type", "amount", "status"
                )
            },
            "before": {"text": before.finding_text, "sha256": expected_old_hash},
            "after": {
                "text": after.finding_text,
                "sha256": sha256(after.finding_text.encode("utf-8")),
            },
        })

    return {
        "source_url": SOURCE_URL,
        "source_sha256": SOURCE_SHA256,
        "source_scope": "FY2024/2025 county assemblies, 47 chapters, 582 findings",
        "baseline_commit": BASE,
        "baseline_extractor_version": 2,
        "corrected_extractor_version": current.EXTRACTOR_VERSION,
        "observed_public_snapshot_sha256": SNAPSHOT_SHA256,
        "changed_rows": rows,
        "unchanged_finding_count": len(new) - len(rows),
        "repair_guard": (
            "Before an authorized ingestion or stored-text update, require this exact PDF SHA256, "
            "the same three row IDs/references/periods/source links, and each before.text SHA256. "
            "Abort on any mismatch; preserve the row identities and all fields outside finding_text. "
            "Reconcile extractions and audits, then verify all three public texts and links."
        ),
        "production_write_performed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--before-snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = make_manifest(args.pdf, args.before_snapshot)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}: {len(manifest['changed_rows'])} guarded row(s)")


if __name__ == "__main__":
    main()
