"""The stalled_projects edition gate (#230).

Red when COB's listing has a newer or re-issued county BIRR than the one
published, when the newest edition has stalled-projects captions and the run
parsed none of them, or when parsed rows were not written. OK only when every
fact it rests on was recorded. Imports only ``seeding.staleness`` and
``models``.

The second half of this file is an adversarial pass's findings against the
first version of the gate, each of which made it answer OK or WARN where it
should have failed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest


class _Session:
    """Newest first, as the gate's query orders them."""

    def __init__(self, *jobs):
        self.jobs = list(jobs)

    def query(self, *a):
        return self

    def filter(self, *a):
        return self

    def order_by(self, *a):
        return self

    def limit(self, n):
        return self

    def all(self):
        return self.jobs

    def first(self):  # the query shape of the first version of the gate
        return self.jobs[0] if self.jobs else None


_T0 = datetime.now(timezone.utc)


def _job(dry_run=False, age=0, **meta):
    return SimpleNamespace(domain="stalled_projects", meta=meta, id=100 - age,
                           dry_run=dry_run, started_at=_T0 - timedelta(days=age))


FP5 = 'content-disposition=attachment;filename="CGBIRR FY 2025_26 August 2026 Final 5.pdf"'
FP6 = FP5.replace("Final 5", "Final 6")
PUBLISHED = {"wpdmdl": 16482, "fiscal_year": "FY2025/26", "period": "annual",
             "as_of": "2026-06-30", "server_fingerprint": FP5}
CURRENT = {"wpdmdl": 16482, "slug": "fy-2025-26", "server_fingerprint": FP5}
HEALTHY = dict(cbirr_listing_newest=CURRENT, cbirr_published=PUBLISHED,
               captions_found=20, rows_parsed=168, rows_written=168)


def _levels(*jobs):
    from seeding.staleness import check_stalled_projects_edition

    return [(f.level, f.message) for f in check_stalled_projects_edition(_Session(*jobs))]


def _worst(*jobs):
    order = {"OK": 0, "WARN": 1, "FAIL": 2}
    return max((lvl for lvl, _ in _levels(*jobs)), key=order.__getitem__)


class TestEditionGate:
    def test_up_to_date_is_ok(self):
        (level, msg), = _levels(_job(**HEALTHY))
        assert level == "OK" and "wpdmdl=16482" in msg

    def test_newer_edition_on_the_listing_is_red(self):
        levels = _levels(_job(cbirr_listing_newest={"wpdmdl": 16500, "slug": "q1-fy-2026-27"},
                              cbirr_published=PUBLISHED, source_mode="refused",
                              source_fallback_reason="download_incomplete", rows_parsed=0))
        (level, msg), = levels
        assert level == "FAIL" and "wpdmdl=16500" in msg and "download_incomplete" in msg

    def test_captions_but_no_rows_is_red(self):
        assert _worst(_job(**dict(HEALTHY, rows_parsed=0, rows_written=0))) == "FAIL"

    def test_nothing_ever_published_is_red(self):
        assert _worst(_job(cbirr_listing_newest=CURRENT, cbirr_published=None)) == "FAIL"

    def test_same_link_reissued_and_not_yet_ingested_is_red(self):
        """COB re-uploads under the same wpdmdl ("... Final 5.pdf" -> "Final
        6"). The ids match; the file does not."""
        levels = _levels(_job(**dict(HEALTHY, cbirr_listing_newest=dict(CURRENT, server_fingerprint=FP6),
                                     source_fallback_reason="download_incomplete",
                                     captions_found=None, rows_parsed=0, rows_written=None)))
        assert [l for l, _ in levels] == ["FAIL"] and "re-issued" in levels[0][1]

    def test_rows_parsed_but_not_written_is_red(self):
        """A live parse that matched no county entity published nothing."""
        assert _worst(_job(**dict(HEALTHY, rows_written=0, unmatched_counties=["Baringo"]))) == "FAIL"

    def test_listing_unread_is_warn_not_ok(self):
        assert _worst(_job(**dict(HEALTHY, cbirr_listing_newest=None))) == "WARN"

    def test_the_nightly_validation_runs_it(self, db_session):
        """Called through run_all — what seed.yml's validate job invokes —
        against a real ingestion_jobs row, not by reading source."""
        from models import IngestionJob, IngestionStatus
        from seeding.staleness import run_all

        db_session.add(IngestionJob(
            domain="stalled_projects", status=IngestionStatus.COMPLETED,
            started_at=datetime.now(timezone.utc).replace(tzinfo=None),
            meta={"cbirr_listing_newest": {"wpdmdl": 16500, "slug": "newer"},
                  "cbirr_published": PUBLISHED, "rows_parsed": 0},
        ))
        db_session.commit()
        mine = [f for f in run_all(db_session) if f.label == "stalled_projects edition"]
        assert [f.level for f in mine] == ["FAIL"]


STALE = dict(cbirr_listing_newest={"wpdmdl": 16500, "slug": "q1"}, cbirr_published=PUBLISHED,
             rows_parsed=0, source_fallback_reason="download_incomplete")


class TestAdversarialFindings:
    """Each of these made the first version answer OK or WARN."""

    @pytest.mark.parametrize(
        "later",
        [
            _job(dry_run=True, since=None),  # cli.py stores no result metadata on a dry run
            _job(since=None),  # a crash: the failure path stores none either
            _job(since=None, dropped_by_global_budget=True),
        ],
        ids=["dry_run", "crash", "budget_dropped"],
    )
    def test_a_run_with_no_verdict_does_not_hide_the_last_real_one(self, later):
        stale = _job(age=1, **STALE)
        assert _worst(later, stale) == "FAIL"

    def test_a_verdictless_latest_run_says_so(self):
        """And still judges the run before it (OK here), rather than
        reporting "listing not read" about a run that recorded nothing."""
        levels = _levels(_job(since=None), _job(age=1, **HEALTHY))
        assert [l for l, _ in levels] == ["WARN", "OK"]
        assert "recorded no verdict" in levels[0][1]

    @pytest.mark.parametrize(
        "listing_fp,published_fp",
        [(FP6, None), (FP6, "__missing__"), (None, FP5), ("", FP5)],
        ids=["published_none", "published_legacy", "probe_failed", "probe_empty"],
    )
    def test_an_unrecorded_fingerprint_is_never_ok(self, listing_fp, published_fp):
        pub = dict(PUBLISHED)
        if published_fp == "__missing__":
            pub.pop("server_fingerprint")
        else:
            pub["server_fingerprint"] = published_fp
        meta = dict(HEALTHY, cbirr_listing_newest=dict(CURRENT, server_fingerprint=listing_fp),
                    cbirr_published=pub)
        assert _worst(_job(**meta)) != "OK"

    def test_no_wpdmdl_on_either_side_is_not_ok(self):
        meta = dict(HEALTHY, cbirr_listing_newest={"slug": "x"}, cbirr_published={"fiscal_year": "FY2025/26"})
        assert _worst(_job(**meta)) != "OK"

    @pytest.mark.parametrize("parsed", ["0", float("nan"), None])
    def test_captions_with_unreadable_row_count_is_red(self, parsed):
        assert _worst(_job(**dict(HEALTHY, rows_parsed=parsed, rows_written=None))) == "FAIL"

    @pytest.mark.parametrize("parsed", [168.0, "168"])
    def test_rows_not_written_is_red_whatever_the_number_type(self, parsed):
        assert _worst(_job(**dict(HEALTHY, rows_parsed=parsed, rows_written=0))) == "FAIL"

    def test_written_not_recorded_is_red(self):
        meta = dict(HEALTHY)
        meta.pop("rows_written")
        assert _worst(_job(**meta)) == "FAIL"

    def test_non_dict_meta_does_not_crash_the_gate(self):
        assert _worst(_job(**dict(HEALTHY, cbirr_listing_newest="16482"))) == "WARN"

    # False reds the pass also found: a gate that is red for no reason is
    # muted, and then it is red for a reason and nobody looks.

    def test_string_ids_compare_as_numbers(self):
        meta = dict(HEALTHY, cbirr_listing_newest=dict(CURRENT, wpdmdl="16482"))
        assert _worst(_job(**meta)) == "OK"

    def test_zero_captions_as_a_string_is_not_red(self):
        meta = dict(HEALTHY, captions_found="0", rows_parsed=0, rows_written=0)
        assert _worst(_job(**meta)) == "OK"

    def test_newest_edition_without_tables_is_warn_not_permanent_red(self):
        meta = dict(STALE, source_fallback_reason="edition_has_no_stalled_tables",
                    refused_edition={"wpdmdl": 16500}, captions_found=0)
        assert _worst(_job(**meta)) == "WARN"
