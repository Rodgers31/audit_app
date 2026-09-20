"""Cross-run cache for the RESULT of parsing a large source PDF.

WHY THIS EXISTS
---------------
``get_or_download_pdf`` stopped the nightly re-downloading the 48MB COB county
BIRR report. It did nothing about re-*parsing* it, which is the larger cost:

    Sep 16  Parsed COB county BIRR PDF (188 records, 251.5s)
    Sep 17  Parsed COB county BIRR PDF (188 records, 249.1s)
    Sep 18  Parsed COB county BIRR PDF (188 records, 258.5s)

~250s of a 1320s global budget — 19% — spent producing the same 188 records
from a document that had not changed. ``pdfplumber`` walks all ~700 pages and
extracts 1,048 tables to find four of them; there is no cheaper way to ask.

So the answer is not to ask again.

WHAT MAKES THIS SAFE
--------------------
A cache over a parse is only as honest as its key, and there are three ways
for the document's bytes alone to be the wrong key:

1. **The document changes.** Handled: the key includes a SHA-256 of the file's
   CONTENT, not its URL or mtime. COB republishing a report under the same
   ``?wpdmdl=`` id still moves the digest. ``tests/test_parse_cache.py``
   flips one byte and asserts a miss.

2. **The parser changes.** This is the trap. A content-keyed cache would go on
   serving a fix's pre-fix output forever, and the fix would look landed while
   production still showed the old numbers. So the key ALSO includes a digest
   of the source file that defines the parse function — derived from the
   function itself via ``inspect``, never a hand-maintained version constant
   that rots the first time someone forgets to bump it. Edit the parser and
   every entry for it is invalidated on the next run.

   When that digest cannot be taken, the cache is BYPASSED rather than keyed
   on a sentinel: a fixed sentinel is a stable key, so two unversionable
   parsers would share an entry and the second would be served the first's
   output — this very failure, reintroduced by its own error path.

3. **The extraction library changes.** ``pdf_parsers.py`` is self-contained
   (``KENYAN_COUNTIES`` and every table helper live in it; its only non-stdlib
   import is ``pdfplumber``), so the digest covers all of OUR code — but the
   tables come out of pdfplumber and pdfminer, and an upgrade changes them
   without touching a byte of our source. Callers pass those versions as
   ``key_extra``.

An entry is not trusted because of its FILENAME. The stored body names the
content digest, the parser digest, the ``key_extra`` and the record count, and
the read path checks every one of them, plus that each record is an object.
A filename is not evidence, and a HIT skips ``_check_county_coverage`` — the
gate that refuses a table missing a county and reconciles the rows against the
report's own printed Total — so a wrong or short entry would publish a figure
the parser itself would have rejected.

A miss is never silent: every outcome logs with the reason (``no_entry``,
``content_changed``, ``parser_changed``, ``unreadable``), so "the cache is
working" and "the cache is quietly wrong" do not look alike in the log. Every
failure of the cache itself — an unwritable directory, an unremovable bad
entry, an unserialisable record — warns and lets the fresh parse through: a
cache problem must never turn a parse the caller could still perform into a
domain failure.

Only records that survive the round trip UNCHANGED are banked, checked against
the exact bytes that get written. ``Decimal`` money values are tagged on the
way out and rebuilt on the way in, because ``float`` would silently change the
figures this project publishes. A tuple, a non-string dict key, or a value
shaped like the Decimal tag would NOT survive — so such records are simply
never cached, and every run reparses, rather than being quietly altered.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, List, Optional

logger = logging.getLogger("seeding.parse_cache")

#: Bumped only when the ENCODING below changes shape. The parser's own
#: identity is tracked by hashing its source, not by this number.
_ENVELOPE_VERSION = 1

#: Marker for a JSON-encoded ``Decimal``. Chosen to be something no parser
#: record would ever use as a real key.
_DECIMAL_TAG = "__decimal__"

_READ_CHUNK = 1024 * 1024


def content_digest(path: Path) -> str:
    """SHA-256 of the file's bytes, streamed so a 48MB PDF is not slurped.

    The 48MB read costs ~0.05s against a ~250s parse, so the digest is free
    relative to what it saves — and unlike mtime or size it actually tracks
    the document.
    """
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(_READ_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def parser_digest(parse_fn: Callable[..., Any]) -> Optional[str]:
    """SHA-256 of the source FILE that defines ``parse_fn``.

    The file, not just the function: a parser is never one function. The CoB
    parse leans on ``extract_all_tables``, ``rank_tables_by_row_anchors``,
    ``stitch_table_continuation``, ``flatten_grouped_headers`` and the county
    canonicaliser, all of which live beside it in ``pdf_parsers.py``. Hashing
    only ``parse``'s own body would leave a fix to any of its helpers serving
    cached pre-fix output.

    Resolved through ``inspect`` rather than a written-down path so it cannot
    drift to the wrong module. If the source cannot be located (a frozen or
    exec'd module, a ``functools.partial``, a mock), returns ``None`` and
    :func:`parse_with_cache` then bypasses the cache entirely.

    ``None``, not a sentinel string: a fixed sentinel is a STABLE key, so two
    different parsers that both fail to resolve would share an entry and the
    second would be served the first's output — which is the very failure
    this digest exists to prevent, reintroduced by the error path. An
    unversioned parser must not be cached at all.
    """
    try:
        source_file = inspect.getsourcefile(parse_fn) or inspect.getfile(parse_fn)
    except TypeError:
        return None
    if not source_file:
        return None
    try:
        return hashlib.sha256(Path(source_file).read_bytes()).hexdigest()
    except OSError:
        return None


def _encode(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {_DECIMAL_TAG: str(value)}
    if isinstance(value, dict):
        return {k: _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {_DECIMAL_TAG}:
            # A malformed tag is corruption, not a value — let the caller
            # treat the whole entry as unreadable rather than substitute
            # something plausible.
            return Decimal(value[_DECIMAL_TAG])
        return {k: _decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(v) for v in value]
    return value


def _entry_path(cache_dir: Path, kind: str, key: str) -> Path:
    return Path(cache_dir) / f"{kind}.{key}.parse.json"


def _key(pdf_digest: str, code_digest: str, extra: str) -> str:
    return hashlib.sha256(
        f"{_ENVELOPE_VERSION}:{pdf_digest}:{code_digest}:{extra}".encode("utf-8")
    ).hexdigest()[:32]


def _verify_envelope(
    payload: Any, pdf_digest: str, code_digest: str, key_extra: str
) -> None:
    """The entry must SAY it is the thing its filename claims.

    The digests were written into the body and then never read, so the
    filename was the only check — and a filename is not evidence. Copy one
    entry over another's path (a bad merge of two cache snapshots, a manual
    rescue, a truncated restore) and the wrong document's records are served
    with the body still naming the document they came from.

    That matters more here than it would for most caches: a fresh parse runs
    ``_check_county_coverage``, which refuses a table missing a county and
    reconciles the rows against the report's own printed Total. A cache HIT
    skips that gate, so a wrong or short entry publishes a county total the
    parser itself would have rejected.
    """
    if not isinstance(payload, dict):
        raise ValueError("entry is not an object")
    if payload.get("version") != _ENVELOPE_VERSION:
        raise ValueError(f"envelope version {payload.get('version')!r}")
    for field, expected in (
        ("content_sha256", pdf_digest),
        ("parser_sha256", code_digest),
        ("key_extra", key_extra),
    ):
        if payload.get(field) != expected:
            raise ValueError(
                f"{field} in the entry is {payload.get(field)!r}, "
                f"not {expected!r} — this entry is for a different input"
            )


def _verify_records(records: Any, payload: Any) -> None:
    """Shape and count, both of which the caller relies on.

    ``record_count`` was written and never read, so an entry could lose rows
    and still be served — and the caller then reports a partial county table
    as a whole one. The caller also does ``record.get(...)`` on every
    element, so a list of non-dicts is an AttributeError deep in the domain
    rather than a cache miss here.
    """
    if not isinstance(records, list):
        raise ValueError("records is not a list")
    stated = payload.get("record_count")
    if stated != len(records):
        raise ValueError(
            f"entry says {stated!r} records but carries {len(records)}"
        )
    bad = next((r for r in records if not isinstance(r, dict)), None)
    if bad is not None:
        raise ValueError(f"records contains a non-object: {bad!r}")


def parse_with_cache(
    pdf_path: Path,
    *,
    cache_dir: Path,
    kind: str,
    parse_fn: Callable[[], List[dict]],
    enabled: bool = True,
    key_extra: str = "",
) -> List[dict]:
    """Return ``parse_fn()``'s records, reusing a cached result when valid.

    ``kind`` names the parse (e.g. ``"cob_county_birr"``) so two parsers over
    the same document do not collide.

    ``key_extra`` is anything OUTSIDE the parser's own source file that can
    change its output — in practice the version of the third-party library
    doing the extraction. ``parser_digest`` covers the module, and the CoB
    parser is self-contained within it (``KENYAN_COUNTIES`` and every table
    helper are defined in ``pdf_parsers.py``, whose only non-stdlib import is
    ``pdfplumber``) — but a pdfplumber upgrade changes what
    ``page.extract_tables()`` returns without touching a byte of our source.
    Without this the upgrade would land and every cached parse would go on
    serving the old library's output. Callers must pass it; the empty default
    exists for parses with no such dependency, not as a convenience.

    The entry is stored beside the PDFs in ``cache_dir`` deliberately: that is
    the directory CI persists with ``actions/cache``, so the cached parse
    travels with the cached document and the two can never be restored apart.
    """
    pdf_path = Path(pdf_path)
    cache_dir = Path(cache_dir)

    if not enabled:
        logger.info("%s parse cache disabled; parsing %s", kind, pdf_path.name)
        return parse_fn()

    pdf_digest = content_digest(pdf_path)
    code_digest = parser_digest(parse_fn)
    if code_digest is None:
        logger.warning(
            "%s parse cache bypassed: the parser's source file could not be "
            "resolved, so its output cannot be versioned. Parsing %s.",
            kind,
            pdf_path.name,
        )
        return parse_fn()

    key = _key(pdf_digest, code_digest, key_extra)
    entry = _entry_path(cache_dir, kind, key)

    if entry.exists():
        try:
            payload = json.loads(entry.read_text(encoding="utf-8"))
            _verify_envelope(payload, pdf_digest, code_digest, key_extra)
            records = _decode(payload["records"])
            _verify_records(records, payload)
        except (OSError, ValueError, KeyError, TypeError, InvalidOperation) as exc:
            logger.warning(
                "%s parse cache entry rejected (%s) — reparsing %s. "
                "reason=unreadable key=%s",
                kind,
                exc,
                pdf_path.name,
                key,
            )
            # Inside the try: the cache directory can be read-only, and a
            # cache problem must never turn a parse the caller could still
            # perform into a domain failure.
            try:
                entry.unlink(missing_ok=True)
            except OSError as unlink_exc:  # pragma: no cover - defensive
                logger.warning(
                    "%s could not remove the rejected entry (%s); it will be "
                    "rejected again next run",
                    kind,
                    unlink_exc,
                )
        else:
            logger.info(
                "%s parse cache HIT (%d records) for %s "
                "[content=%s parser=%s] — skipping the reparse",
                kind,
                len(records),
                pdf_path.name,
                pdf_digest[:12],
                code_digest[:12],
            )
            return records
    else:
        logger.info(
            "%s parse cache MISS for %s [content=%s parser=%s] reason=%s",
            kind,
            pdf_path.name,
            pdf_digest[:12],
            code_digest[:12],
            _miss_reason(cache_dir, kind, pdf_digest, code_digest),
        )

    records = parse_fn()

    # Never bank a result the parse did not produce. An empty list is a real
    # outcome the caller treats as failure (it falls back to the fixture), and
    # caching it would make one bad night permanent for the TTL of the CI
    # cache.
    if not records:
        logger.info(
            "%s parse produced no records — not cached, so the next run "
            "retries instead of inheriting the emptiness",
            kind,
        )
        return records

    # Only cache what survives the round trip UNCHANGED — checked against the
    # EXACT BYTES that will be written, not against an in-memory
    # encode/decode pair.
    #
    # That distinction is the whole value of the check. ``_encode`` turns a
    # tuple into a list, so an encode/decode comparison catches tuples; it
    # does not touch dict KEYS, and it is ``json.dumps`` that silently turns
    # ``{1: "Q1"}`` into ``{"1": "Q1"}``. A check that skipped the
    # serialisation passed that case and served the altered record. Round-
    # tripping the real text catches tuples, non-string keys, and a field
    # that happens to be shaped like the Decimal tag, in one comparison.
    #
    # Today's CoB records are str / Decimal / float / None and survive
    # exactly — verified against all 188 from the real document. Checking it
    # rather than asserting it means a future field that does not survive is
    # reparsed every run instead of being quietly changed.
    payload = {
        "version": _ENVELOPE_VERSION,
        "kind": kind,
        "source_name": pdf_path.name,
        "content_sha256": pdf_digest,
        "parser_sha256": code_digest,
        "key_extra": key_extra,
        "record_count": len(records),
        "records": _encode(records),
    }
    try:
        text = json.dumps(payload)
        restored = _decode(json.loads(text)["records"])
    except (TypeError, ValueError) as exc:
        logger.warning(
            "%s parse NOT cached: the records are not JSON-serialisable "
            "(%s). Serving the fresh parse.",
            kind,
            exc,
        )
        return records
    if restored != records:
        logger.warning(
            "%s parse NOT cached: the records do not survive the JSON round "
            "trip unchanged (a tuple, a non-string dict key, or a value "
            "shaped like the Decimal tag). Serving the fresh parse; every "
            "run will reparse until the record shape is JSON-safe.",
            kind,
        )
        return records

    _store(entry, kind, text, len(records))
    return records


def _miss_reason(
    cache_dir: Path, kind: str, pdf_digest: str, code_digest: str
) -> str:
    """Say WHICH half of the key moved, so a miss is diagnosable.

    A run that reparses because COB published a new report and one that
    reparses because a cache directory was never restored are different
    events, and a log that calls both "miss" cannot tell an operator which
    one happened.
    """
    try:
        siblings = list(Path(cache_dir).glob(f"{kind}.*.parse.json"))
    except OSError:
        return "no_entry"
    if not siblings:
        return "no_entry"
    saw_content = saw_parser = False
    for path in siblings:
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if meta.get("parser_sha256") == code_digest:
            saw_parser = True
        if meta.get("content_sha256") == pdf_digest:
            saw_content = True
    if saw_parser and not saw_content:
        return "content_changed"
    if saw_content and not saw_parser:
        return "parser_changed"
    return "no_entry"


def _store(entry: Path, kind: str, text: str, count: int) -> None:
    """Write ``text`` to ``entry`` atomically; a failure warns, never raises.

    Takes the already-serialised text rather than the payload, so the bytes
    that land on disk are byte-for-byte the ones the caller verified survive
    the round trip. Serialising a second time here would leave room for the
    stored entry and the checked one to differ.

    Atomic because this directory is restored wholesale by CI: a half-written
    entry from an interrupted run would be indistinguishable from a good one
    on the next night, and would be read as data.
    """
    tmp_fd = None
    tmp_name: Optional[str] = None
    try:
        entry.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=str(entry.parent), prefix=f".{kind}.", suffix=".tmp"
        )
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            tmp_fd = None
            handle.write(text)
        os.replace(tmp_name, entry)
        tmp_name = None
        logger.info(
            "%s parse cached (%d records) at %s", kind, count, entry.name
        )
    except (OSError, TypeError, ValueError) as exc:
        logger.warning(
            "%s parse could not be cached (%s) — the next run will reparse",
            kind,
            exc,
        )
    finally:
        if tmp_fd is not None:  # pragma: no cover - defensive
            os.close(tmp_fd)
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:  # pragma: no cover - defensive
                pass


__all__ = ["parse_with_cache", "content_digest", "parser_digest"]
