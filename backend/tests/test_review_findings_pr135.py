"""Regression fixtures for the Copilot review findings on PR #135.

Written BEFORE their fixes and seen to fail against the pre-fix code.

PR #135's whole purpose is to stop publishing figures that trace to nothing.
Every finding below is a place where that purpose was not carried through — an
absence still rendered as a number, or a claim of evidence the code does not
have:

* **G4** peers with no publishable amounts contribute ``0`` to
  ``region_avg_flagged_amount`` and a default ``"A"`` to ``region_avg_grade``.
  The population-bracket path thirty lines below already guards this correctly
  ("a peer with no recorded amount is unknown, not 0") — the region path does
  not, so the same endpoint answers the same question two different ways.
* **G5** ``_parse_amount`` converts a missing or malformed amount to ``0.0``
  and the case is then published with ``amount: 0`` — a manufactured zero for
  a *sourced* case.
* **G6** ``/verify/audits`` stamps ``verification_status="verified"`` on a row
  that only passed the publication gate, which by its own docstring does not
  fetch the URL, check md5, or require a page locator.
* **G10** ``page_ref="   "`` and ``page_number=0`` pass as provenance.
* **G11** ``count_withheld_audits`` returns one total for two different
  withholding causes, and every caller labels it "source document has no URL".
"""

from __future__ import annotations

import pytest


# ── G10: a page locator must actually locate a page ──────────────────
class TestPageReferenceValidation:
    @pytest.mark.parametrize(
        "case",
        [
            {"page_ref": "   ", "page_number": None},
            {"page_ref": "\t\n", "page_number": None},
            {"page_ref": None, "page_number": 0},
            {"page_ref": None, "page_number": -3},
            {"page_ref": None, "page_number": "0"},
        ],
    )
    def test_a_locator_that_cannot_locate_is_refused(self, case, monkeypatch):
        """RED before the fix: the check was ``in (None, "")``, so whitespace
        and page 0 both read as "present". A reader sent to page 0 of a
        400-page report has not been given a source."""
        from services.publication_gate import missing_funds_provenance_failure

        class _Doc:
            url = "https://example.invalid/report.pdf"
            title = "A Report"

        full = {"source_document_id": 1, **case}
        assert (
            missing_funds_provenance_failure(full, {1: _Doc()})
            == "no_page_reference"
        )

    def test_a_real_locator_still_passes(self):
        """POSITIVE CONTROL — the gate must not start refusing valid cases."""
        from services.publication_gate import missing_funds_provenance_failure

        class _Doc:
            url = "https://example.invalid/report.pdf"
            title = "A Report"

        for good in ({"page_ref": "p. 42"}, {"page_number": 42},
                     {"page_number": "42"}):
            case = {"source_document_id": 1, **good}
            assert missing_funds_provenance_failure(case, {1: _Doc()}) is None, good


# ── G11: two causes must not be reported as one ──────────────────────
class TestWithheldReasonsAreDistinguished:
    def test_counts_are_broken_down_by_reason(self, db_session, seed_country,
                                              seed_source_doc):
        """RED before the fix: ``count_withheld_audits`` returned a bare int,
        and callers labelled the whole total "source document has no
        resolvable URL" — so a row withheld for unreadable ``(cid:NN)`` text
        was reported under a reason that did not apply to it.

        The backfill already distinguishes the two (``no_url_count`` vs
        ``withheld_cid``), which is what makes the runtime collapse a defect
        rather than a limitation.
        """
        from models import Audit, Entity, EntityType, Severity
        from services.publication_gate import count_withheld_by_reason

        from datetime import date

        from models import FiscalPeriod

        entity = Entity(
            country_id=seed_country.id, type=EntityType.COUNTY,
            canonical_name="Testville County", slug="testville-county",
        )
        period = FiscalPeriod(
            country_id=seed_country.id, label="FY 2024/25",
            start_date=date(2024, 7, 1), end_date=date(2025, 6, 30),
        )
        db_session.add_all([entity, period])
        db_session.flush()

        # Withheld for the FIRST reason: the source document has no URL.
        seed_source_doc.url = None
        db_session.add(
            Audit(entity_id=entity.id, period_id=period.id,
                  source_document_id=seed_source_doc.id,
                  finding_text="a normal finding", severity=Severity.INFO)
        )
        db_session.commit()

        breakdown = count_withheld_by_reason(db_session)
        assert isinstance(breakdown, dict)
        assert breakdown.get("source_document_has_no_url", 0) >= 1
        assert "finding_text_unreadable_cid" in breakdown

    def test_the_total_still_matches_the_sum(self, db_session, seed_country,
                                             seed_source_doc):
        """The breakdown must not drift from the number callers already
        report; a reason-aware count that disagrees with the total would be a
        new inconsistency, not a fix."""
        from services.publication_gate import (
            count_withheld_audits,
            count_withheld_by_reason,
        )

        assert sum(count_withheld_by_reason(db_session).values()) == (
            count_withheld_audits(db_session)
        )


# ── G6: passing a gate is not verification ───────────────────────────
class TestVerificationIsNotOverstated:
    def test_the_gate_alone_does_not_earn_verified(self):
        """RED before the fix: the audits branch set
        ``verification_status="verified"`` after only
        ``publishable_audit_criterion()``.

        That gate's own docstring lists what it does NOT do: it never fetches
        the URL, never checks md5, and never requires a page locator. Calling
        the result "verified" tells a reader the evidence was checked when
        nothing was.
        """
        import inspect

        from routers import data_provenance

        src = inspect.getsource(data_provenance)
        start = src.index('elif table_name == "audits"')
        nxt = src.find("elif table_name ==", start + 10)
        audits_branch = src[start : nxt if nxt != -1 else len(src)]
        assert 'verification_status = "verified"' not in audits_branch, (
            "the audits branch still claims 'verified' on gate-only evidence"
        )


# ── G4 / G5: absence is not zero, and not an A ───────────────────────
def _main_source() -> str:
    """Read main.py from disk.

    Deliberately not ``inspect.getsource(main)``: main.py is ~11k lines and
    importing it outside the suite's conftest performs real startup work,
    which hung the first version of these tests.
    """
    import pathlib as _p

    return (_p.Path(__file__).resolve().parents[1] / "main.py").read_text()


class TestAbsenceIsNotZero:
    @pytest.mark.parametrize(
        "raw",
        [None, "", "   ", "n/a", "unknown", "KES", [], {}, True, False, "abc"],
    )
    def test_an_unreadable_amount_is_none_not_zero(self, raw):
        """RED before the fix: every one of these became ``0.0`` and was
        published as a real figure on a SOURCED case — the worst version of a
        manufactured zero, because the citation makes it look confirmed.

        ``True``/``False`` are in the list because a bool is an int in Python,
        so ``float(True) == 1.0`` would have published KES 1.
        """
        from main import _parse_missing_funds_amount

        assert _parse_missing_funds_amount(raw) is None, repr(raw)

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("KES 1.5B", 1.5e9), ("2.4M", 2.4e6), ("900K", 9.0e5),
            ("1,234", 1234.0), (5000, 5000.0), (12.5, 12.5),
        ],
    )
    def test_a_readable_amount_still_parses(self, raw, expected):
        """POSITIVE CONTROL — returning None must not become the answer for
        everything."""
        from main import _parse_missing_funds_amount

        assert _parse_missing_funds_amount(raw) == pytest.approx(expected)

    def test_the_caller_withholds_rather_than_publishing_the_none(self):
        assert 'withheld_by_reason["amount_unreadable"]' in _main_source()

    def test_a_peer_with_no_amount_does_not_pull_the_region_average_down(self):
        """RED before the fix: ``float(pa.amount or 0)`` summed an unknown as
        0 and appended unconditionally, so peers about which nothing is known
        were averaged in as if they had flagged nothing."""
        src = _main_source()
        assert "float(pa.amount or 0) for pa in peer_audits" not in src, (
            "the region path still coerces an unknown peer amount to 0"
        )
        assert (
            "_peer_amounts = [float(pa.amount) for pa in peer_audits "
            "if pa.amount is not None]" in src
        )

    def test_a_peer_with_no_opinion_is_not_graded_a(self):
        """RED before the fix: ``region_grades.append(pg)`` sat OUTSIDE the
        ``if peer_opinions:`` guard, so the scan's starting value "A" was
        recorded as a verdict for a peer with no audit opinions at all."""
        import re as _re

        src = _main_source()
        at = src.index("region_grades.append(pg)")
        block = src[max(0, at - 700) : at + 40]
        guard = _re.search(r"\n( *)if peer_opinions:", block)
        append = _re.search(r"\n( *)region_grades\.append", block)
        assert guard and append, "could not locate the guard/append pair"
        assert len(append.group(1)) > len(guard.group(1)), (
            "region_grades.append is outside the `if peer_opinions:` guard, so "
            "a peer with no opinion is still graded A"
        )
