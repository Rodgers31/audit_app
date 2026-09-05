"""Bootstrap's reference data has to be inside the deployed image.

WHAT WENT WRONG
---------------
``DATA_DIR`` was ``Path(__file__).resolve().parent.parent / "apis"``, which is
true of a git checkout and false of the container. The backend image is built
with ``context: ./backend`` (docker-build-deploy.yml) and
``COPY . .`` into ``/app``, so ``bootstrap.py`` lands at ``/app/bootstrap.py``
and DATA_DIR resolves to ``/apis`` — a path nothing ever writes.

Anything outside ``backend/`` is not in that build context and CANNOT ship,
so no amount of path juggling helps: the files have to live in the package.

The result was a lie in the freshness record. Every restart of the production
web process recorded::

    source_fallback_reason: fixture_missing
    source_fallback_detail: absent from the repo: oag_audit_data.json, ...

The files are in the repo. They were absent from that deployment, which is a
different fault with a different fix, and the message sent you looking for a
deleted file. It also stamped the domain's freshness record, so production's
no-op run overwrote the reason from the weekly job that does have the data.
"""

from pathlib import Path

import pytest

import bootstrap

BACKEND = Path(bootstrap.__file__).resolve().parent


class TestTheFilesShip:
    @pytest.mark.parametrize("name", sorted(bootstrap._FIXTURE_DECLARATIONS))
    def test_every_declared_fixture_is_inside_the_backend_package(self, name):
        """The build context is ./backend — outside it cannot be copied."""
        path = bootstrap.DATA_DIR / name

        assert path.exists(), f"{name} is not where bootstrap looks"
        assert BACKEND in path.resolve().parents, (
            f"{path} is outside {BACKEND}, so it cannot ship in an image built "
            "with context ./backend"
        )

    def test_the_data_dir_does_not_depend_on_a_parent_directory(self):
        """The specific bug: a path that climbs out of the package.

        ``/app/bootstrap.py`` has no meaningful parent, so any candidate above
        the backend directory resolves to somewhere nothing ever put a file.
        """
        assert BACKEND in bootstrap.DATA_DIR.resolve().parents or (
            bootstrap.DATA_DIR.resolve() == BACKEND
        ), f"{bootstrap.DATA_DIR} escapes {BACKEND}"


class TestTheDiagnosisIsAccurate:
    def test_an_unresolvable_directory_is_not_reported_as_absent_from_the_repo(
        self, monkeypatch, tmp_path
    ):
        """"absent from the repo" was false and sent you to the wrong place."""
        monkeypatch.setattr(bootstrap, "DATA_DIR", tmp_path / "nowhere")
        for attr in ("AUDIT_DATA_PATH", "NATIONAL_AUDIT_PATH", "COUNTY_DATA_PATH"):
            monkeypatch.setattr(
                bootstrap,
                attr,
                tmp_path / "nowhere" / getattr(bootstrap, attr).name,
            )

        p = bootstrap.bootstrap_provenance()

        assert p["source_fallback_reason"] == "fixture_missing"
        assert "absent from the repo" not in p["source_fallback_detail"]
        # It must name the directory it actually looked in, so the next reader
        # knows whether to look for a deleted file or a packaging fault.
        assert "nowhere" in p["source_fallback_detail"]

    def test_the_directory_it_used_is_recorded(self):
        """Which directory answered is part of the run's provenance."""
        p = bootstrap.bootstrap_provenance()

        assert p["data_dir"] == str(bootstrap.DATA_DIR)


class TestItIsConfigurable:
    def test_an_env_var_overrides_the_packaged_directory(self, tmp_path, monkeypatch):
        """A deployment that mounts the data elsewhere needs a way to say so."""
        monkeypatch.setenv("BOOTSTRAP_DATA_DIR", str(tmp_path))

        assert bootstrap.resolve_data_dir() == tmp_path

    def test_an_unset_env_var_falls_back_to_the_packaged_directory(self, monkeypatch):
        monkeypatch.delenv("BOOTSTRAP_DATA_DIR", raising=False)

        assert bootstrap.resolve_data_dir() == BACKEND / "data" / "reference"


class TestNothingExcludesThemFromTheImage:
    """Living in backend/ is necessary but not sufficient — .dockerignore
    still gets a veto, and it already excludes two sibling data directories
    (``data/seeding/``, ``data/pending_bills_cache/``). A pattern that grew to
    cover ``data/`` would put us straight back to ``fixture_missing`` with
    nothing in the test suite noticing.
    """

    @staticmethod
    def _patterns(path: Path):
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                yield line

    def test_dockerignore_does_not_exclude_the_reference_data(self):
        import fnmatch

        dockerignore = BACKEND / ".dockerignore"
        assert dockerignore.exists(), "backend build context has no .dockerignore"

        rel = bootstrap.DATA_DIR.resolve().relative_to(BACKEND)
        targets = [str(rel / name) for name in bootstrap._FIXTURE_DECLARATIONS]
        targets.append(str(rel))

        offenders = []
        for pattern in self._patterns(dockerignore):
            if pattern.startswith("!"):  # a re-include cannot exclude
                continue
            bare = pattern.rstrip("/")
            for target in targets:
                # Docker matches a pattern against the path and against every
                # parent directory of it, which is how "data/seeding/" hides
                # everything beneath it.
                parts = target.split("/")
                prefixes = ["/".join(parts[: i + 1]) for i in range(len(parts))]
                if any(fnmatch.fnmatch(p, bare) for p in prefixes):
                    offenders.append((pattern, target))

        assert not offenders, (
            "backend/.dockerignore excludes the reference data from the image: "
            f"{offenders}"
        )
