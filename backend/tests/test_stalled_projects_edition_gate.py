"""The stalled_projects edition gate (#230).

Red when COB's listing has a newer county BIRR than the one published, or
when the newest edition has stalled-projects captions and the run parsed none
of them. Imports only ``seeding.staleness`` and ``models``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace


class _Session:
    def __init__(self, job):
        self.job = job

    def query(self, *a):
        return self

    def filter(self, *a):
        return self

    def order_by(self, *a):
        return self

    def first(self):
        return self.job


def _job(**meta):
    return SimpleNamespace(domain="stalled_projects", meta=meta, id=1,
                           started_at=datetime.now(timezone.utc))


class TestEditionGate:
    def _levels(self, job):
        from seeding.staleness import check_stalled_projects_edition

        return [(f.level, f.message) for f in check_stalled_projects_edition(_Session(job))]

    PUBLISHED = {"wpdmdl": 16482, "fiscal_year": "FY2025/26", "period": "annual", "as_of": "2026-06-30"}

    def test_up_to_date_is_ok(self):
        (level, msg), = self._levels(_job(cbirr_listing_newest={"wpdmdl": 16482},
                                          cbirr_published=self.PUBLISHED,
                                          captions_found=20, rows_parsed=168))
        assert level == "OK" and "wpdmdl=16482" in msg

    def test_newer_edition_on_the_listing_is_red(self):
        (level, msg), = self._levels(_job(cbirr_listing_newest={"wpdmdl": 16500, "slug": "q1-fy-2026-27"},
                                          cbirr_published=self.PUBLISHED, source_mode="refused",
                                          source_fallback_reason="download_incomplete",
                                          captions_found=None, rows_parsed=0))
        assert level == "FAIL" and "wpdmdl=16500" in msg and "download_incomplete" in msg

    def test_captions_but_no_rows_is_red(self):
        levels = self._levels(_job(cbirr_listing_newest={"wpdmdl": 16482},
                                   cbirr_published=self.PUBLISHED, captions_found=20, rows_parsed=0))
        assert ("FAIL" in {l for l, _ in levels})

    def test_nothing_ever_published_is_red(self):
        (level, _), = self._levels(_job(cbirr_listing_newest={"wpdmdl": 16482}, cbirr_published=None))
        assert level == "FAIL"

    def test_same_link_reissued_and_not_yet_ingested_is_red(self):
        """COB re-uploads under the same wpdmdl ("... Final 5.pdf" -> "Final
        6"). The ids match; the file does not."""
        (level, msg), = self._levels(_job(
            cbirr_listing_newest={"wpdmdl": 16482, "server_fingerprint": 'filename="Final 6.pdf"'},
            cbirr_published=dict(self.PUBLISHED, server_fingerprint='filename="Final 5.pdf"'),
            source_fallback_reason="download_incomplete", captions_found=None, rows_parsed=0,
        ))
        assert level == "FAIL" and "re-issued" in msg

    def test_rows_parsed_but_not_written_is_red(self):
        """A live parse that matched no county entity published nothing."""
        levels = self._levels(_job(
            cbirr_listing_newest={"wpdmdl": 16482}, cbirr_published=self.PUBLISHED,
            captions_found=20, rows_parsed=168, rows_written=0,
            unmatched_counties=["Baringo", "Kericho"],
        ))
        assert [l for l, _ in levels] == ["FAIL"]

    def test_listing_unread_is_warn_not_ok(self):
        (level, _), = self._levels(_job(cbirr_listing_newest=None, cbirr_published=self.PUBLISHED))
        assert level == "WARN"

    def test_the_nightly_validation_runs_it(self, db_session):
        """Called through run_all — what seed.yml's validate job invokes —
        against a real ingestion_jobs row, not by reading source."""
        from models import IngestionJob, IngestionStatus
        from seeding.staleness import run_all

        db_session.add(IngestionJob(
            domain="stalled_projects", status=IngestionStatus.COMPLETED,
            started_at=datetime.now(timezone.utc).replace(tzinfo=None),
            meta={"cbirr_listing_newest": {"wpdmdl": 16500, "slug": "newer"},
                  "cbirr_published": self.PUBLISHED, "rows_parsed": 0},
        ))
        db_session.commit()
        mine = [f for f in run_all(db_session) if f.label == "stalled_projects edition"]
        assert [f.level for f in mine] == ["FAIL"]
