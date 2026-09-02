"""The weekly Sunday job must be visible to the freshness gates.

Issue #137 P3. ``seed.yml`` runs ``initialize_reference_data()`` directly
(``seed.yml:283-284``), outside the seeding CLI. It therefore records no
``IngestionJob`` and emits no freshness mark::

    backend/bootstrap.py       mark_live/mark_fixture: 0   IngestionJob: 0
    backend/bootstrap_data.py  mark_live/mark_fixture: 0   IngestionJob: 0

So ``check_ingestion_freshness`` cannot see it at all, and it re-seeds from
three git-tracked files every Sunday:

===================================  ===========  ==============
file                                 last commit  age at 2026-09-02
===================================  ===========  ==============
apis/oag_audit_data.json             2025-09-05   362 days
apis/oag_national_audit_data.json    2026-02-21   192 days
apis/enhanced_county_data.json       2026-02-24   189 days
===================================  ===========  ==============

That is the silently-frozen-fixture shape the nightly instrumentation exists to
eliminate, running weekly with nothing watching.

This file does NOT change what publishes. In particular it does not give these
documents a URL: ``_ensure_source_document`` in bootstrap.py takes no ``url``
parameter at all (5 call sites, 0 pass one), so every document it creates has
``url = NULL`` and every audit citing one is withheld for
``source_document_has_no_url``. Adding URLs would flip 26 withheld findings to
published, which is a product decision, not a test fixture. It is recorded as
P1 in #137. What this pins is that the job STATES its own provenance, so the
frozen fixture is visible rather than silent.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

_APIS = Path(__file__).resolve().parents[2] / "apis"
_FIXTURES = [
    "oag_audit_data.json",
    "oag_national_audit_data.json",
    "enhanced_county_data.json",
]


class TestTheBootstrapDeclaresItsInputs:
    def test_every_fixture_it_reads_is_described(self):
        """RED before the fix: ``bootstrap_provenance()`` did not exist, so
        nothing named these files, their digests, or their age."""
        from bootstrap import bootstrap_provenance

        prov = bootstrap_provenance()
        named = {f["file"] for f in prov["files"]}
        assert named == set(_FIXTURES), (
            f"provenance names {sorted(named)}, expected {sorted(_FIXTURES)}"
        )

    def test_each_file_carries_a_digest_and_an_age(self):
        from bootstrap import bootstrap_provenance

        for entry in bootstrap_provenance()["files"]:
            path = _APIS / entry["file"]
            assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest(), (
                f"{entry['file']}: recorded digest does not match the file on disk"
            )
            assert isinstance(entry["age_days"], int) and entry["age_days"] >= 0
            assert entry["data_date"], f"{entry['file']} declares no data date"
            assert entry["bytes"] == path.stat().st_size

    def test_the_mode_is_declared_fixture_not_live(self):
        """The whole point. A run that reads git-tracked JSON must not be
        indistinguishable from one that fetched from a publisher."""
        from bootstrap import bootstrap_provenance

        assert bootstrap_provenance()["source_mode"] == "fixture"

    def test_a_stale_fixture_is_flagged_rather_than_merely_recorded(self):
        """A digest nobody compares is not observability. The provenance names
        which files exceed the staleness threshold, so a gate — or a human
        reading the job row — sees the problem without doing arithmetic."""
        from bootstrap import STALE_AFTER_DAYS, bootstrap_provenance

        prov = bootstrap_provenance()
        expected = {
            f["file"] for f in prov["files"] if f["age_days"] > STALE_AFTER_DAYS
        }
        assert set(prov["stale_files"]) == expected
        assert prov["is_stale"] is bool(expected)

    def test_the_year_old_oag_fixture_is_currently_flagged(self):
        """POSITIVE CONTROL. If this ever passes vacuously — because every file
        was refreshed, or the threshold was raised to hide them — the assertion
        above is still true but no longer proves anything."""
        from bootstrap import bootstrap_provenance

        prov = bootstrap_provenance()
        oag = next(f for f in prov["files"] if f["file"] == "oag_audit_data.json")
        assert oag["age_days"] > 180, (
            f"oag_audit_data.json is {oag['age_days']} days old; if it was "
            "genuinely refreshed, delete this test with the commit that did it"
        )
        assert "oag_audit_data.json" in prov["stale_files"]


class TestTheDeclarationIsHonest:
    def test_no_file_is_claimed_to_have_a_live_source_it_lacks(self):
        """Each file declares either the seeding domain that supersedes it or
        ``no_live_source``.

        The claim is checked against the REGISTRY, not merely asserted to be a
        string. A declaration naming a domain that does not exist would be
        decoration — the same defect class as the health check that probed a
        host nothing fetches (#137 P5).
        """
        from bootstrap import bootstrap_provenance
        from seeding.registries import REGISTRY, load_builtin_domains

        load_builtin_domains()
        registered = set(REGISTRY.domains())
        assert registered, "the domain registry is empty — this check is vacuous"

        for entry in bootstrap_provenance()["files"]:
            claim = entry.get("live_source")
            assert claim, f"{entry['file']} declares no live_source"
            if claim != "no_live_source":
                assert claim in registered, (
                    f"{entry['file']} claims domain '{claim}' supersedes it, "
                    f"but no such domain is registered: {sorted(registered)}"
                )

    def test_the_provenance_is_json_serialisable(self):
        """It is written into IngestionJob.metadata, which is JSONB."""
        from bootstrap import bootstrap_provenance

        json.dumps(bootstrap_provenance())


class TestTheDeclaredDateCannotDrift:
    """``oag_audit_data.json`` carries no metadata, so its date is declared in
    code. A declaration nothing checks is how the original defect happened."""

    def test_the_declared_date_matches_git(self):
        import subprocess

        from bootstrap import _FIXTURE_DECLARATIONS

        repo = Path(__file__).resolve().parents[2]
        try:
            subprocess.run(
                ["git", "rev-parse", "--git-dir"], cwd=repo,
                capture_output=True, check=True,
            )
        except Exception:
            pytest.skip("not a git checkout")

        for name, spec in _FIXTURE_DECLARATIONS.items():
            if spec.get("date_field"):
                continue  # the file states its own date; nothing to drift
            out = subprocess.run(
                ["git", "log", "-1", "--format=%ad", "--date=short",
                 "--", f"apis/{name}"],
                cwd=repo, capture_output=True, text=True,
            ).stdout.strip()
            if not out:
                pytest.skip(f"no git history for {name}")
            assert spec["declared_date"] == out, (
                f"{name}: declared {spec['declared_date']}, last committed "
                f"{out}. Update the declaration in the commit that refreshes "
                "the file."
            )


class TestTheRunIsRecorded:
    def test_a_job_row_is_written_with_the_provenance(self, monkeypatch, tmp_path):
        """RED before the fix: `grep -c IngestionJob backend/bootstrap.py` was
        0, so `check_ingestion_freshness` had nothing to look at."""
        import bootstrap
        from models import Base, IngestionJob, IngestionStatus
        from sqlalchemy import create_engine
        from sqlalchemy.dialects.postgresql import JSONB
        from sqlalchemy.ext.compiler import compiles
        from sqlalchemy.orm import sessionmaker

        @compiles(JSONB, "sqlite")
        def _c(t, c, **kw):  # pragma: no cover
            return "TEXT"

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        Sess = sessionmaker(bind=engine)
        monkeypatch.setattr(bootstrap, "SessionLocal", Sess)

        try:
            bootstrap.initialize_reference_data()
        except Exception as exc:  # noqa: BLE001
            # A partial seed is fine here; what must hold is that the run left
            # a row either way. A job visible only on success would make an
            # outage look like a week that never ran.
            print(f"(seed raised, which is acceptable for this assertion: {exc})")

        with Sess() as s:
            jobs = (
                s.query(IngestionJob)
                .filter(IngestionJob.domain == bootstrap.BOOTSTRAP_DOMAIN)
                .all()
            )
        assert jobs, "the bootstrap left no IngestionJob row"
        job = jobs[-1]
        assert job.status in (IngestionStatus.COMPLETED, IngestionStatus.FAILED)
        assert (job.meta or {}).get("source_mode") == "fixture"
