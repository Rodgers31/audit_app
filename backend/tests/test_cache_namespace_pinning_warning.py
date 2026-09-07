"""A constant CACHE_VERSION silently disables per-deploy cache scoping.

``CACHE_VERSION`` takes precedence over ``RENDER_GIT_COMMIT``. A value typed
into the Render dashboard is a CONSTANT, so setting one pins every deploy to
the same namespace and reintroduces exactly the cross-deploy staleness the
scope was added to prevent:

    CACHE_VERSION=v1 set
      deploy aaaa111 -> 'v1'   deploy bbbb222 -> 'v1'    (same scope)
    CACHE_VERSION unset
      deploy aaaa111 -> 'aaaa111...'  deploy bbbb222 -> 'bbbb222...'

It is worse than leaving it unset, because the health report then reads
``source: CACHE_VERSION``, which looks correctly configured. ``source:
fallback`` is at least a visible warning sign.

So the one genuinely self-defeating configuration announces itself.

THE FALSE POSITIVE THAT MATTERS. ``CACHE_VERSION=$RENDER_GIT_COMMIT`` in the
start command is the RECOMMENDED fix when Render does not expose the commit to
the process directly. Both variables are then set, and the scope still advances
per deploy — warning about it would train the reader to ignore the warning, so
the check fires only when the two are UNRELATED.
"""

from __future__ import annotations

import subprocess
import sys


COMMIT = "3f52280abcdef1234567890abcdef1234567890a"


def _resolve(monkeypatch, cache_version=None, render_commit=None):
    import cache.redis_cache as rc

    for name, value in (("CACHE_VERSION", cache_version), ("RENDER_GIT_COMMIT", render_commit)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    return rc._resolve_cache_namespace()


class TestAPinnedScopeAnnouncesItself:
    def test_an_unrelated_cache_version_is_flagged(self, monkeypatch):
        """RED before this change: no warning, and nothing distinguishes this
        from a correctly scoped deploy."""
        namespace, source, warning = _resolve(
            monkeypatch, cache_version="v1", render_commit=COMMIT
        )
        assert namespace == "v1"
        assert source == "CACHE_VERSION"
        assert warning, (
            "CACHE_VERSION=v1 overrides a per-deploy commit with a constant, "
            "so every future deploy shares one cache scope — and nothing says so"
        )
        assert "RENDER_GIT_COMMIT" in warning, warning

    def test_a_version_derived_from_the_commit_is_not_flagged(self, monkeypatch):
        """The recommended start-command fix must stay quiet.

        Warning here would be a false positive on the one configuration we tell
        people to use, which is how warnings get ignored.
        """
        for derived in (COMMIT, COMMIT[:12], f"v2-{COMMIT}"):
            _, source, warning = _resolve(
                monkeypatch, cache_version=derived, render_commit=COMMIT
            )
            assert source == "CACHE_VERSION"
            assert warning is None, (
                f"CACHE_VERSION={derived!r} still advances with the commit, so "
                f"it is correctly configured, but it was flagged: {warning!r}"
            )

    def test_cache_version_alone_is_not_flagged(self, monkeypatch):
        """Nothing is being overridden — it is the only lever available."""
        _, source, warning = _resolve(monkeypatch, cache_version="v1")
        assert source == "CACHE_VERSION"
        assert warning is None, warning

    def test_the_commit_path_is_not_flagged(self, monkeypatch):
        _, source, warning = _resolve(monkeypatch, render_commit=COMMIT)
        assert source == "RENDER_GIT_COMMIT"
        assert warning is None, warning

    def test_the_fallback_is_not_flagged_here(self, monkeypatch):
        """The fallback is already reported through ``source``; a second
        warning for it would be noise."""
        _, source, warning = _resolve(monkeypatch)
        assert source.startswith("fallback")
        assert warning is None, warning


class TestTheWarningReachesTheLogAndTheEndpoint:
    def test_it_is_logged_at_import(self):
        """Verified in a real process, not inferred from the return value."""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import logging, sys; "
                "logging.basicConfig(level=logging.WARNING); "
                "sys.path.insert(0, '.'); "
                "import cache.redis_cache",
            ],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "CACHE_VERSION": "v1", "RENDER_GIT_COMMIT": COMMIT},
        )
        combined = result.stdout + result.stderr
        # Without this the test would pass forever if the subprocess simply
        # failed to import the module: no output looks like no warning.
        assert result.returncode == 0, (
            f"the subprocess did not import the module at all:\n{combined[-2000:]}"
        )
        assert "CACHE_VERSION" in combined and "deploy" in combined.lower(), (
            "importing the module with a pinned scope produced no warning:\n"
            f"{combined[-2000:]}"
        )

    def test_health_check_reports_it(self):
        """A log line alone is what let #184 hide; the report is queryable."""
        from cache.redis_cache import RedisCache

        cache = RedisCache.__new__(RedisCache)
        cache.client = None
        cache._memory_cache = {}
        cache.namespace = "v1"
        cache.namespace_source = "CACHE_VERSION"
        cache.namespace_warning = "pinned: CACHE_VERSION overrides RENDER_GIT_COMMIT"

        health = cache.health_check()
        assert health.get("cache_namespace_warning"), (
            f"the pinned scope is invisible to anything but the logs: {health!r}"
        )

    def test_health_check_omits_it_when_there_is_nothing_to_say(self):
        """POSITIVE CONTROL — the field must not always be present, or it
        carries no information."""
        from cache.redis_cache import RedisCache

        cache = RedisCache.__new__(RedisCache)
        cache.client = None
        cache._memory_cache = {}
        cache.namespace = "abcdef123456"
        cache.namespace_source = "RENDER_GIT_COMMIT"
        cache.namespace_warning = None

        assert "cache_namespace_warning" not in cache.health_check()
