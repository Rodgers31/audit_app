"""Tests for provenance-based data vintage (audit §2.9 / §3.7).

Locks in that ``last_updated`` is derived from the source document's real
vintage (publication_date in meta, else fetch_date) and never the request
time.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace

import pytest

from provenance import _parse_dt, doc_vintage, resolve_data_vintage

BACKEND_DIR = Path(__file__).resolve().parent.parent


# ── _parse_dt ───────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "value,expected",
    [
        ("2025-04-30", dt.datetime(2025, 4, 30)),
        ("2025-04", dt.datetime(2025, 4, 1)),
        ("2024", dt.datetime(2024, 1, 1)),
        (dt.date(2023, 6, 1), dt.datetime(2023, 6, 1)),
        (None, None),
        ("", None),
        ("not-a-date", None),
    ],
)
def test_parse_dt(value, expected):
    assert _parse_dt(value) == expected


# ── doc_vintage: publication_date preferred, fetch_date fallback ────────
def test_doc_vintage_prefers_publication_date():
    doc = SimpleNamespace(
        meta={"publication_date": "2025-04-30"},
        fetch_date=dt.datetime(2026, 6, 1),
    )
    assert doc_vintage(doc) == dt.datetime(2025, 4, 30)


def test_doc_vintage_falls_back_to_fetch_date():
    doc = SimpleNamespace(meta={}, fetch_date=dt.datetime(2026, 1, 15))
    assert doc_vintage(doc) == dt.datetime(2026, 1, 15)


def test_doc_vintage_none_doc():
    assert doc_vintage(None) is None


# ── resolve_data_vintage: max across docs, honest None ──────────────────
class _FakeQuery:
    def __init__(self, docs):
        self._docs = docs

    def filter(self, *a, **k):
        return self

    def all(self):
        return self._docs


class _FakeDB:
    def __init__(self, docs):
        self._docs = docs

    def query(self, *a, **k):
        return _FakeQuery(self._docs)


def test_resolve_returns_most_recent_vintage():
    docs = [
        SimpleNamespace(id=1, meta={"publication_date": "2025-04-30"}, fetch_date=None),
        SimpleNamespace(id=2, meta={}, fetch_date=dt.datetime(2026, 2, 20)),
    ]
    assert resolve_data_vintage(_FakeDB(docs), [1, 2]) == dt.datetime(2026, 2, 20)


def test_resolve_empty_ids_is_none():
    assert resolve_data_vintage(_FakeDB([]), []) is None
    assert resolve_data_vintage(_FakeDB([]), [None, None]) is None


def test_resolve_no_resolvable_vintage_is_none():
    docs = [SimpleNamespace(id=1, meta={}, fetch_date=None)]
    assert resolve_data_vintage(_FakeDB(docs), [1]) is None


def test_resolve_mixes_aware_and_naive_without_error():
    docs = [
        SimpleNamespace(
            id=1,
            meta={},
            fetch_date=dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc),
        ),
        SimpleNamespace(id=2, meta={}, fetch_date=dt.datetime(2026, 1, 1)),
    ]
    # Must not raise on aware/naive comparison; 2026 is the latest.
    assert resolve_data_vintage(_FakeDB(docs), [1, 2]).year == 2026


# ── /debt/national wired to the helper (no request-time last_updated) ───
def test_debt_national_uses_vintage_helper_not_now():
    src = (BACKEND_DIR / "main.py").read_text(encoding="utf-8")
    # The endpoint must resolve vintage from provenance and serve it as
    # last_updated, rather than stamping the response with the request time.
    # (Other endpoints still on datetime.now() are tracked as the rest of
    # the 0.2 freshness work; this asserts the /debt/national fix only.)
    assert "resolve_data_vintage(" in src
    assert '"last_updated": _vintage_iso,' in src
