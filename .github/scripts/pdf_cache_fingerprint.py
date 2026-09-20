#!/usr/bin/env python3
"""Fingerprint the seeding PDF cache, so a save key tracks BANKABLE PROGRESS.

Why this file exists
--------------------
PR #175 keyed the nightly's ``actions/cache`` save on::

    find backend/data/seeding/cache/pdfs -maxdepth 1 -name '*.pdf' \
      -printf '%f\n' | sort | sha256sum | cut -c1-16

That counts *completed ``.pdf`` filenames only*. Three kinds of real progress
are invisible to it, and all three are the progress this cache exists to keep:

1. ``<sha256(url)>.part`` — a resumable partial download. A night that pulls
   27MB of a 48MB PDF and is then killed by the seed budget ends with exactly
   the filename set it started with, so it produces the same fingerprint,
   collides with the existing key, and saves nothing. The 27MB is discarded
   and the next night starts from the same offset. OBSERVED on runs
   34799406076 / 34921218282 / 35048000013 / 35174426953 / 35299414702:
   ``resuming from 27751154 bytes`` on four consecutive nights, byte-identical,
   each preceded by ``Failed to save: Unable to reserve cache with key
   seed-pdf-cache-2026-w38-c72cd0b7025eea9d``.

2. ``<sha256(url)>.json`` — the TTL sidecar. Its ``created_at`` is what makes a
   cached PDF count as fresh. Re-downloading a document rewrites the sidecar
   but not the filename set, so a refreshed TTL could never be banked either.
   That is why the five OAG documents (24h TTL, ``cache_ttl_seconds``) missed
   the cache on every night after the snapshot they were first saved in.

3. A ``.pdf`` whose CONTENT changed under the same name (the publisher
   re-issued the document at the same URL).

The rule here is therefore: every file in the directory contributes. Small
files (the sidecars) contribute their bytes, because that is where
``created_at`` lives; large files contribute their size, because for a
``.part`` the size IS the progress and for a ``.pdf`` the name is already a
SHA-256 of its URL.

Portability
-----------
``find -printf`` is a GNU extension: on BSD/macOS ``find`` exits 1 with
"unknown primary or operator", and the ``2>/dev/null`` in the old step turned
that into an empty fingerprint rather than an error. Doing this in Python
means the step behaves identically on a developer's machine and on the runner,
which is what lets ``backend/tests/test_pdf_cache_banks_progress.py`` execute
the real thing instead of asserting on the YAML text.

Usage::

    pdf_cache_fingerprint.py <cache-dir> [key-prefix]

Output (to ``$GITHUB_OUTPUT`` when set, else stdout)::

    fingerprint=<16 hex chars>
    key=<key-prefix><16 hex chars>
    files=<count of files in the cache dir>
    bytes=<total size>

``key`` is emitted whole so the workflow can both save under it and compare it
against the restored entry in one ``if:``, instead of rebuilding it with
``format()`` inside a YAML folded scalar — where a more-indented continuation
line is preserved literally and quietly puts a newline in the middle of the
expression.

``files`` is load-bearing, not decoration: the caller MUST NOT save a cache
that holds nothing. ``actions/cache`` restores the newest entry matching the
prefix, so storing an empty directory — which is what a run that died before
its first download would otherwise do, under ``if: always()`` — would become
the newest entry and wipe out every banked partial on the following night.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

#: Files at or below this size contribute their full contents to the digest.
#: The TTL sidecars are ~60 bytes; the documents are 0.6-50MB. Nothing in
#: between is expected, so this cleanly separates "bookkeeping, hash it" from
#: "payload, its size is enough".
SMALL_FILE_BYTES = 64 * 1024


def fingerprint(cache_dir: Path) -> tuple[str, int, int]:
    """Return ``(fingerprint, file_count, total_bytes)`` for ``cache_dir``.

    A missing directory is not an error — it is the state of a repository that
    has never run a seed — and yields a count of 0 so the caller can decline to
    save it. It is reported as its own digest rather than as a zero or a
    sentinel string, because "no cache directory" and "a cache directory that
    happens to hash to X" must not be able to collide.
    """
    entries: list[str] = []
    total = 0
    if cache_dir.is_dir():
        for path in sorted(cache_dir.iterdir(), key=lambda p: p.name):
            if not path.is_file():
                continue
            size = path.stat().st_size
            total += size
            if size <= SMALL_FILE_BYTES:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                entries.append(f"{path.name}\0{size}\0{digest}")
            else:
                entries.append(f"{path.name}\0{size}")
    payload = "\n".join(entries).encode("utf-8")
    # The count is inside the digest as well as beside it, so a directory of
    # N files can never fingerprint like a directory of M.
    stamp = hashlib.sha256(f"{len(entries)}\n".encode("utf-8") + payload)
    return stamp.hexdigest()[:16], len(entries), total


def main(argv: list[str]) -> int:
    cache_dir = Path(argv[1] if len(argv) > 1 else "backend/data/seeding/cache/pdfs")
    prefix = argv[2] if len(argv) > 2 else ""
    fp, count, total = fingerprint(cache_dir)
    lines = [
        f"fingerprint={fp}",
        f"key={prefix}{fp}",
        f"files={count}",
        f"bytes={total}",
    ]
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
