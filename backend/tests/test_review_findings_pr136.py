"""Regression fixtures for the Copilot review findings on PR #136.

Each test here was written BEFORE its fix and seen to fail against the
pre-fix code — that is the whole point, per `regression-fixture-on-fix`. A
test written after the fix asserts the implementation rather than the defect,
and the finding recurs under a different shape with the suite still green.

The findings, and why each is a real defect rather than a pattern-match:

* **F4** ``d1a7c9e40b12``'s downgrade drops ``users.display_name`` /
  ``email_verified`` / ``updated_at`` even when the BASELINE created them
  (``21d0394c1d6b:160,163``). Same invariant as the ``confidence_score``
  defect fixed in ``b3d8ab47bf3b`` — reintroduced by the migration written to
  fix it.
* **F5** ``check_ingestion_freshness(domains=None)`` — the nightly's path via
  ``run_all`` — iterates only domains that ALREADY have a recent job, so its
  "no run recorded" warning cannot fire for the outage it exists to detect.
* **F7** ``%%EOF`` was accepted anywhere in the last 2 KB, so a truncated
  incrementally-updated PDF passes whenever an older marker lands near the cut.
* **F11** ``_fresh_cache_hit`` returned a cached PDF without ever running the
  completeness check, so an entry written by the magic-bytes-only implementation
  keeps serving a truncated file for the 30-day TTL.
* **F3** ``mark_live`` was recorded for a run that refreshed only a SECONDARY
  series, and ``check_ingestion_freshness`` reports any live mode as OK — so a
  domain whose published figure is frozen reads healthy forever.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 9, 2, tzinfo=timezone.utc)


# ── F4: a downgrade must not drop columns it did not add ─────────────
class TestMigrationDowngradeKeepsBaselineColumns:
    def test_the_baseline_owns_the_three_users_columns(self):
        """The premise: if the baseline creates them, 3d's upgrade is a no-op
        on a clean replay and its downgrade has nothing of its own to drop."""
        import pathlib

        baseline = (
            pathlib.Path(__file__).resolve().parents[1]
            / "alembic/versions/21d0394c1d6b_baseline_full_schema_from_models_py.py"
        ).read_text()
        for col in ("display_name", "email_verified", "updated_at"):
            assert f"'{col}'" in baseline, col

    def test_downgrade_drops_nothing(self):
        """RED before the fix: ``downgrade()`` dropped whatever it found.

        A migration cannot know at downgrade time whether ITS upgrade created
        a column or the baseline did — the two run in different processes, and
        nothing records it. So the safe direction is the one
        ``b3d8ab47bf3b`` already settled for ``confidence_score``: never drop.
        An extra column is harmless; a missing one is a runtime error, and the
        downgrade's job is to leave a WORKING ``cdfb80379a29`` schema on both
        paths.

        Driven through the module's own helpers with a stubbed
        ``information_schema`` result, so the assertion is about the DECISION
        rather than about SQL round-tripping.
        """
        from tests._migration_harness import run_migration_downgrade

        dropped = run_migration_downgrade(
            "d1a7c9e40b12_stage1_3d_restore_the_users_columns",
            existing_columns={"display_name", "email_verified", "updated_at",
                              "id", "email", "roles"},
        )
        assert dropped == [], (
            f"downgrade dropped {dropped}; on a clean replay those are "
            f"baseline-owned and the schema at cdfb80379a29 would then be "
            f"missing columns models.User selects"
        )

    def test_upgrade_still_adds_the_columns_when_they_are_missing(self):
        """POSITIVE CONTROL — a never-drop downgrade must not be achieved by
        making the migration inert. On production (where the baseline never
        ran) the upgrade is the whole point."""
        from tests._migration_harness import run_migration_upgrade

        added = run_migration_upgrade(
            "d1a7c9e40b12_stage1_3d_restore_the_users_columns",
            existing_columns={"id", "email", "roles", "password_hash",
                              "created_at", "disabled"},
        )
        assert sorted(added) == ["display_name", "email_verified", "updated_at"]

    def test_upgrade_is_a_noop_when_the_columns_already_exist(self):
        from tests._migration_harness import run_migration_upgrade

        added = run_migration_upgrade(
            "d1a7c9e40b12_stage1_3d_restore_the_users_columns",
            existing_columns={"display_name", "email_verified", "updated_at",
                              "id", "email", "roles"},
        )
        assert added == []


# ── F5: the outage warning must be reachable ─────────────────────────
class TestFreshnessWatchesTheRegistryNotJustRunners:
    def test_a_domain_with_no_run_at_all_is_reported(self, db_session):
        """RED before the fix: ``watched = sorted(seen)`` only contained
        domains that HAD a job, so a domain that stopped running entirely
        vanished from validation instead of raising the warning written for
        exactly that case."""
        from models import IngestionJob, IngestionStatus
        from seeding.staleness import check_ingestion_freshness

        db_session.add(
            IngestionJob(
                domain="fiscal_summary",
                status=IngestionStatus.COMPLETED,
                dry_run=False,
                started_at=(NOW - timedelta(days=1)).replace(tzinfo=None),
                items_processed=1, items_created=0, items_updated=1,
                errors=[], meta={"source_mode": "live"},
            )
        )
        db_session.commit()

        findings = check_ingestion_freshness(db_session, now=NOW)
        labels = {f.label for f in findings}
        # national_debt is registered but has NO job row at all.
        assert "national_debt ingestion" in labels, (
            "a registered domain that never ran is invisible to the nightly; "
            f"only saw {sorted(labels)}"
        )
        missing = next(f for f in findings if f.label == "national_debt ingestion")
        assert missing.level == "WARN"
        assert "no run recorded" in missing.message

    def test_an_explicit_domain_list_is_still_honoured(self, db_session):
        """The fix must not break the caller that passes its own list."""
        from seeding.staleness import check_ingestion_freshness

        findings = check_ingestion_freshness(
            db_session, now=NOW, domains=["only_this_one"]
        )
        assert [f.label for f in findings] == ["only_this_one ingestion"]


# ── F7 / F11: truncation must not survive, and must not be cached ────
class TestPdfCompleteness:
    def _write(self, tmp_path, body: bytes):
        p = tmp_path / "doc.pdf"
        p.write_bytes(body)
        return p

    def test_a_stale_eof_near_the_cut_is_not_whole(self, tmp_path):
        """RED before the fix: ``%%EOF`` anywhere in the last 2 KB passed.

        An incrementally-updated PDF carries a marker per revision. Truncate
        the final revision shortly after the PREVIOUS marker and the old
        scanner declares the file complete — which, for a resumable download
        with no Content-Length, means it STOPS and caches the truncation.
        """
        from seeding.pdf_download import _looks_like_whole_pdf

        truncated = b"%PDF-1.7\n" + b"a" * 500 + b"%%EOF\n" + b"b" * 300
        assert _looks_like_whole_pdf(self._write(tmp_path, truncated)) is False

    def test_a_genuinely_complete_pdf_is_still_whole(self, tmp_path):
        """POSITIVE CONTROL: real government PDFs end with the marker plus
        trailing whitespace (verified against the 5 real files downloaded on
        2026-08-29, e.g. b'...startxref\\r\\n29637223\\r\\n%%EOF\\r\\n')."""
        from seeding.pdf_download import _looks_like_whole_pdf

        for tail in (b"%%EOF", b"%%EOF\n", b"%%EOF\r\n", b"%%EOF   \n\n"):
            body = b"%PDF-1.7\n" + b"x" * 100 + b"\nstartxref\n123\n" + tail
            assert _looks_like_whole_pdf(self._write(tmp_path, body)) is True, tail

    def test_a_cache_hit_is_validated_not_trusted(self, tmp_path):
        """RED before the fix: ``_fresh_cache_hit`` returned on size+TTL alone.

        A truncated entry written by the magic-bytes-only implementation kept
        being served for the whole 30-day TTL — and the CI cache is restored
        across runs with a rolling key, so such entries really do persist.
        """
        import json, time

        from seeding.pdf_download import _cache_paths, _fresh_cache_hit

        url = "https://example.invalid/report.pdf"
        pdf_path, meta_path = _cache_paths(tmp_path, url)
        pdf_path.write_bytes(b"%PDF-1.7\n" + b"z" * 4000)  # magic ok, no EOF
        meta_path.write_text(json.dumps({"url": url, "created_at": time.time()}))

        assert _fresh_cache_hit(pdf_path, meta_path, 86_400) is None, (
            "a truncated cache entry was accepted as a hit"
        )

    def test_a_whole_cached_pdf_is_still_a_hit(self, tmp_path):
        """POSITIVE CONTROL — the fix must not disable the cache."""
        import json, time

        from seeding.pdf_download import _cache_paths, _fresh_cache_hit

        url = "https://example.invalid/whole.pdf"
        pdf_path, meta_path = _cache_paths(tmp_path, url)
        pdf_path.write_bytes(b"%PDF-1.7\n" + b"z" * 100 + b"\n%%EOF\n")
        meta_path.write_text(json.dumps({"url": url, "created_at": time.time()}))

        assert _fresh_cache_hit(pdf_path, meta_path, 86_400) is not None


# ── F3: "live" must mean the PUBLISHED figure moved ──────────────────
class TestPartialRefreshIsNotHealthy:
    def test_a_secondary_only_refresh_is_not_reported_as_ok(self, db_session):
        """RED before the fix: ``revenue_by_source`` recorded source_mode=live
        when only the World Bank headline totals refreshed, while the tax-head
        breakdown this domain PUBLISHES stayed on the fixture. The gate keys
        on the mode and never reads the detail, so it reported OK forever."""
        from models import IngestionJob, IngestionStatus
        from seeding.staleness import check_ingestion_freshness

        db_session.add(
            IngestionJob(
                domain="revenue_by_source",
                status=IngestionStatus.COMPLETED,
                dry_run=False,
                started_at=(NOW - timedelta(days=1)).replace(tzinfo=None),
                items_processed=1, items_created=0, items_updated=1,
                errors=[],
                meta={
                    "source_mode": "partial",
                    "source_fallback_reason": "kra_overlay_not_promoted",
                },
            )
        )
        db_session.commit()

        finding = next(
            f for f in check_ingestion_freshness(db_session, now=NOW,
                                                 domains=["revenue_by_source"])
        )
        assert finding.level == "WARN", (
            "a run that refreshed only a secondary series reported as healthy"
        )
        assert "kra_overlay_not_promoted" in finding.message

    def test_a_fully_live_run_is_still_ok(self, db_session):
        """POSITIVE CONTROL — WARN must not become the answer for everything."""
        from models import IngestionJob, IngestionStatus
        from seeding.staleness import check_ingestion_freshness

        db_session.add(
            IngestionJob(
                domain="debt_timeline",
                status=IngestionStatus.COMPLETED,
                dry_run=False,
                started_at=(NOW - timedelta(days=1)).replace(tzinfo=None),
                items_processed=1, items_created=0, items_updated=1,
                errors=[], meta={"source_mode": "live"},
            )
        )
        db_session.commit()
        finding = next(
            f for f in check_ingestion_freshness(db_session, now=NOW,
                                                 domains=["debt_timeline"])
        )
        assert finding.level == "OK"

    def test_mark_partial_records_a_distinct_mode(self):
        from seeding import freshness

        freshness.reset("revenue_by_source")
        freshness.mark_partial(
            "revenue_by_source",
            reason="kra_overlay_not_promoted",
            detail="World Bank totals refreshed; tax-head breakdown is fixture",
        )
        rec = freshness.get("revenue_by_source")
        assert rec["mode"] == freshness.PARTIAL
        assert rec["reason"] == "kra_overlay_not_promoted"
        # is_stale must be TRUE: the published figure did not move.
        assert freshness.is_stale("revenue_by_source") is True


# ── F6: 206 is not proof the bytes start where we asked ──────────────
class _HeaderedStream:
    """httpx-like streaming response that carries headers."""

    def __init__(self, body: bytes, status: int = 200, headers: dict | None = None):
        self.body, self.status_code = body, status
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        return None

    def iter_bytes(self):
        yield self.body


class _RecordingClient:
    def __init__(self, responder):
        self._responder = responder
        self.sent_headers: list[dict] = []

    def stream(self, method, url, headers=None, timeout=None):
        self.sent_headers.append(dict(headers or {}))
        return self._responder(dict(headers or {}))


def _wrap(fake):
    from contextlib import nullcontext

    from seeding.http_client import SeedingHttpClient

    obj = object.__new__(SeedingHttpClient)
    obj._client = fake

    class _NullLimiter:
        def context(self):
            return nullcontext()

    obj._rate_limiter = _NullLimiter()
    return obj


WHOLE = b"%PDF-1.7\n" + b"x" * 400 + b"\ntrailer\n%%EOF\n"


class TestResumeRangeSafety:
    def test_a_206_starting_at_the_wrong_offset_restarts(self, tmp_path):
        """RED before the fix: only ``status_code != 206`` was checked, so a
        server answering 206 from a DIFFERENT offset had its bytes appended at
        the wrong position. The spliced file still begins with ``%PDF-`` and
        can still end with ``%%EOF``, so neither existing guard catches it."""
        part = tmp_path / "doc.part"
        dest = tmp_path / "doc.pdf"
        part.write_bytes(WHOLE[:200])  # a resume in progress

        def responder(headers):
            assert headers.get("Range") == "bytes=200-"
            # Server honours "partial content" but from byte 0, not 200.
            return _HeaderedStream(
                WHOLE, status=206,
                headers={"Content-Range": f"bytes 0-{len(WHOLE)-1}/{len(WHOLE)}"},
            )

        client = _wrap(_RecordingClient(responder))
        client.download_to_file("u", dest, max_seconds=5, resume_part=part,
                                completion_check=lambda p: False)
        # Restarted from zero => exactly the body, not 200 bytes of prefix
        # plus the whole document spliced on the end.
        got = dest.read_bytes()
        assert got == WHOLE, (
            f"expected a clean restart; got {len(got)} bytes (a spliced "
            f"prefix + body would be {200 + len(WHOLE)})"
        )

    def test_a_206_at_the_right_offset_still_appends(self, tmp_path):
        """POSITIVE CONTROL — the fix must not disable resumption, which is
        the whole reason the COB downloads work at all."""
        part = tmp_path / "doc.part"
        dest = tmp_path / "doc.pdf"
        part.write_bytes(WHOLE[:200])

        def responder(headers):
            return _HeaderedStream(
                WHOLE[200:], status=206,
                headers={"Content-Range": f"bytes 200-{len(WHOLE)-1}/{len(WHOLE)}"},
            )

        client = _wrap(_RecordingClient(responder))
        client.download_to_file("u", dest, max_seconds=5, resume_part=part,
                                completion_check=lambda p: False)
        assert dest.read_bytes() == WHOLE

    def test_a_206_without_content_range_appends_but_warns(self, tmp_path, caplog):
        """A non-compliant 206 must NOT hard-restart.

        cob.go.ke — the server the whole resume feature exists for — could not
        be re-probed (its TLS certificate expired 2026-09-02), and turning a
        working resume into an endless 12MB re-download would be a worse bug
        than the one being fixed. So an absent Content-Range keeps the previous
        behaviour and says so loudly; only a header that DISAGREES restarts.
        """
        import logging

        part = tmp_path / "doc.part"
        dest = tmp_path / "doc.pdf"
        part.write_bytes(WHOLE[:200])

        client = _wrap(_RecordingClient(
            lambda h: _HeaderedStream(WHOLE[200:], status=206)  # no header
        ))
        with caplog.at_level(logging.WARNING):
            client.download_to_file("u", dest, max_seconds=5, resume_part=part,
                                    completion_check=lambda p: False)
        assert dest.read_bytes() == WHOLE          # appended, not restarted
        assert "NO Content-Range" in caplog.text   # and not silently

    def test_if_range_is_sent_so_a_reissued_document_cannot_be_spliced(self, tmp_path):
        """RED before the fix: no validator was persisted or sent, so a
        publisher re-issuing the file between nightly runs would have an old
        prefix spliced onto a new suffix."""
        part = tmp_path / "doc.part"
        dest = tmp_path / "doc.pdf"

        # Pass 1: record the entity's ETag alongside the partial.
        fake1 = _RecordingClient(
            lambda h: _HeaderedStream(WHOLE, status=200, headers={"ETag": '"v1"'})
        )
        _wrap(fake1).download_to_file("u", dest, max_seconds=5, resume_part=part,
                                      completion_check=lambda p: False)
        part.write_bytes(WHOLE[:200])  # simulate an interrupted follow-up

        # Pass 2: the resume must carry If-Range with that validator.
        fake2 = _RecordingClient(
            lambda h: _HeaderedStream(
                WHOLE[200:], status=206,
                headers={"Content-Range": f"bytes 200-{len(WHOLE)-1}/{len(WHOLE)}"},
            )
        )
        _wrap(fake2).download_to_file("u", dest, max_seconds=5, resume_part=part,
                                      completion_check=lambda p: False)
        assert fake2.sent_headers[0].get("If-Range") == '"v1"', (
            f"no If-Range sent; headers were {fake2.sent_headers[0]}"
        )


# ── F8: a response must not declare a unit its rows contradict ───────
class TestUnitDeclarationsAgree:
    """RED before the fix: rows carried ``unit: "KES"`` (raw, since the 3a
    migration) while the SAME response declared ``_meta.unit="billion_kes"``.

    A client that trusts response-level metadata — the field that exists to be
    trusted — scales by 1e9 in the wrong direction. This is the same units
    hazard that forced the production migration to be rolled back on
    2026-08-30, in a second place.
    """

    def _fiscal(self, db_session):
        import asyncio

        from main import clear_all_caches, get_fiscal_summary

        clear_all_caches()
        return asyncio.run(get_fiscal_summary(db=db_session))

    def _timeline(self, db_session):
        import asyncio

        from main import clear_all_caches, get_debt_timeline

        clear_all_caches()
        return asyncio.run(get_debt_timeline(db=db_session))

    def test_fiscal_summary_meta_unit_matches_its_rows(
        self, db_session, seed_country, seed_source_doc
    ):
        from models import FiscalSummary

        db_session.add(
            FiscalSummary(
                fiscal_year="FY 2025/26",
                appropriated_budget=4690e9, total_revenue=2910e9,
                total_borrowing=910e9, county_allocation=415e9,
                unit="KES", source_document_id=seed_source_doc.id,
            )
        )
        db_session.commit()
        body = self._fiscal(db_session)
        assert body["current"]["unit"] == "KES"
        assert body["_meta"]["unit"] == "KES", (
            f'_meta.unit={body["_meta"]["unit"]!r} contradicts the row unit '
            f'"KES"; a client scaling by the response metadata is 1e9 out'
        )

    def test_debt_timeline_meta_unit_matches_its_rows(
        self, db_session, seed_country, seed_source_doc
    ):
        from models import DebtTimeline

        db_session.add(
            DebtTimeline(
                year=2025, external=5462e9, domestic=6837e9, total=12299e9,
                unit="KES", source_document_id=seed_source_doc.id,
            )
        )
        db_session.commit()
        body = self._timeline(db_session)
        assert body["_meta"]["unit"] == "KES"

    def test_the_declaration_is_derived_not_hardcoded(self):
        """POSITIVE CONTROL: flipping the constant to "KES" would pass the two
        tests above and still lie on an UN-migrated database, whose rows carry
        no unit and are bare billions.

        Exercised on the helper rather than the endpoint because
        ``fiscal_summaries.unit`` is ``NOT NULL DEFAULT 'KES'`` — the ORM can
        never yield the pre-migration shape, so the endpoint cannot express
        this case at all.
        """
        from main import _declared_row_unit

        class _Row:
            def __init__(self, unit):
                self.unit = unit

        assert _declared_row_unit([_Row("KES"), _Row("KES")]) == "KES"
        # Pre-migration: no unit recorded -> still billions.
        assert _declared_row_unit([_Row(None), _Row(None)]) == "billion_kes"
        # Mixed mid-migration -> the conservative answer, never a silent rescale.
        assert _declared_row_unit([_Row("KES"), _Row(None)]) == "billion_kes"
        # No rows at all -> the default, not a crash.
        assert _declared_row_unit([]) == "billion_kes"
