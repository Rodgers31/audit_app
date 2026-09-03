"""The nightly health check must probe the hosts the nightly actually fetches.

Issue #137 P5. ``seed.yml``'s health check carried a hand-written registry of
URLs that had drifted from the pipeline it is supposed to be checking:

* it probed ``https://newsite.treasury.go.ke/``, which appears ONLY in
  ``etl/kenya_pipeline.py`` and ``etl/smoke_test.py`` — the legacy ETL. The
  nightly runs ``python -m seeding.cli seed --all`` (``seed.yml:378``), and
  ``seeding/config.py`` fetches ``www.treasury.go.ke``. Both hosts answer 200,
  so the probe was green while telling us nothing about the host in use.
* ``https://www.treasury.go.ke/budget-books/`` — the source of the FY2026/27
  enacted budget, Tier-1 since #136 — was not probed at all.

The registry stays a literal list in bash: the health-check job has no checkout
and no Python, and giving it both to import ``seeding.config`` would trade a
30-second job for a dependency install. What it cannot be allowed to do is
DRIFT, so the coupling is enforced here instead, where the dependencies are
already installed.
"""

from __future__ import annotations

import pathlib
import re
from urllib.parse import urlparse

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[2]
_WORKFLOW = _REPO / ".github" / "workflows" / "seed.yml"

# Hosts the health check probes on purpose although ``seeding/config.py``
# declares no default for them. Each needs a reason; an entry without one is
# how a stale probe survives.
PROBED_WITHOUT_A_CONFIG_DEFAULT = {
    # audits/fetcher.py:54-56,201 hardcodes these rather than reading config.
    "www.oagkenya.go.ke": "seeding/domains/audits/fetcher.py:54",
    # Cross-check source for debt; no default because it is only consulted
    # when the CBK figure is missing.
    "www.imf.org": "debt cross-check, consulted opportunistically",
}


def _probed_urls() -> list:
    """URLs from the ``SOURCES=( ... )`` array in the health-check step."""
    text = _WORKFLOW.read_text()
    block = re.search(r"SOURCES=\(\s*(.*?)\n\s*\)", text, re.S)
    assert block, "could not find the SOURCES=( ... ) array in seed.yml"
    return re.findall(r'"[^"|]*\|([^"|]+)\|', block.group(1))


def _config_default_urls() -> dict:
    """``{url: "Class.field"}`` for every http default in seeding.config."""
    import seeding.config as C

    out = {}
    for name in dir(C):
        fields = getattr(getattr(C, name), "model_fields", None)
        if not fields:
            continue
        for fname, field in fields.items():
            default = getattr(field, "default", None)
            if isinstance(default, str) and default.startswith("http"):
                out[default] = f"{name}.{fname}"
    return out


class TestEveryFetchedHostIsProbed:
    def test_no_configured_host_goes_unprobed(self):
        """RED before the fix: www.treasury.go.ke was fetched by four settings
        and probed by none — the probe pointed at newsite. instead."""
        probed = {urlparse(u).netloc for u in _probed_urls()}
        missing = {
            urlparse(url).netloc: where
            for url, where in _config_default_urls().items()
            if urlparse(url).netloc not in probed
        }
        assert not missing, (
            "seeding/config.py fetches these hosts, and the nightly health "
            "check does not probe them:\n  "
            + "\n  ".join(f"{h}  ({w})" for h, w in sorted(missing.items()))
        )

    def test_the_budget_books_page_is_probed(self):
        """Tier-1 since #136: it is where the enacted FY2026/27 budget comes
        from, so losing it silently is how a fiscal year stops arriving."""
        assert any(
            "treasury.go.ke" in u and "budget-books" in u for u in _probed_urls()
        ), "the Treasury budget-books listing is not in the health-check registry"

    def test_no_probe_points_at_a_host_the_pipeline_never_fetches(self):
        """The other direction, which is what let ``newsite.`` sit here for
        months: a probe against an unused host is green regardless of whether
        ingestion works, and reads as reassurance."""
        fetched = {urlparse(u).netloc for u in _config_default_urls()}
        stray = {
            host
            for host in (urlparse(u).netloc for u in _probed_urls())
            if host not in fetched and host not in PROBED_WITHOUT_A_CONFIG_DEFAULT
        }
        assert not stray, (
            "these hosts are probed but nothing in seeding/config.py fetches "
            "them — drop them, or record why they are probed in "
            f"PROBED_WITHOUT_A_CONFIG_DEFAULT: {sorted(stray)}"
        )


class TestTheRegistryIsParseable:
    """Anti-vacuity: every assertion above passes trivially if the parse
    returns nothing."""

    def test_the_workflow_exists_and_yields_urls(self):
        urls = _probed_urls()
        assert len(urls) >= 8, f"only parsed {len(urls)} URLs from seed.yml"
        assert all(u.startswith("http") for u in urls)

    def test_config_yields_the_hosts_the_pipeline_is_built_on(self):
        """Named hosts rather than a count. A threshold is calibrated to
        whichever branch it was written on — this one was `>= 8`, which was
        true of the branch that added budget-books and false of main — and a
        count says nothing about WHICH settings were read."""
        from urllib.parse import urlparse

        hosts = {urlparse(u).netloc for u in _config_default_urls()}
        for required in ("cob.go.ke", "www.treasury.go.ke", "www.centralbank.go.ke"):
            assert required in hosts, (
                f"{required} is absent from seeding.config defaults — either "
                "the introspection broke, or the pipeline stopped fetching it "
                "and this file's assertions are now vacuous"
            )
