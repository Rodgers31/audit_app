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


class TestTheRemediationGuidanceIsNotWrong:
    """#138 fixed the PROBE. It left the instructions beside it wrong.

    When the health check fails, the notify job files an issue carrying a
    "Common URL Migrations" table. That table told a maintainer to migrate
    Treasury from ``treasury.go.ke/`` TO ``newsite.treasury.go.ke/`` — the
    legacy host, the one #138 had just removed. Acting on it would have
    reverted the fix, in the file the issue itself names two lines earlier
    (``backend/seeding/config.py``).

    A probe pointed at the wrong host is silently green. Advice pointed at
    the wrong host is worse: someone follows it.
    """

    def _guidance(self) -> str:
        text = _WORKFLOW.read_text()
        block = re.search(r"### Common URL Migrations(.*?)`---`", text, re.S)
        assert block, "could not find the URL-migration guidance in seed.yml"
        return block.group(1)

    def _migration_targets(self) -> dict:
        """``{site: host}`` from the New Pattern column — where the issue
        sends a maintainer. The Old Pattern column is allowed to name a dead
        host; that is what it is for."""
        out = {}
        for line in self._guidance().splitlines():
            cells = line.split("|")
            if len(cells) < 5 or "---" in line or "Old Pattern" in line:
                continue
            hosts = re.findall(r"[a-z0-9.-]+\.go\.ke", cells[3])
            if hosts:
                out[cells[1].strip(" `\\")] = hosts[0]
        return out

    def test_the_guidance_does_not_send_anyone_to_an_unfetched_host(self):
        # Hosts reached by config default OR hardcoded in a fetcher — the
        # guidance may legitimately name either. Only a host the pipeline
        # touches nowhere is a stray.
        fetched = {urlparse(u).netloc for u in _config_default_urls()}
        fetched |= set(PROBED_WITHOUT_A_CONFIG_DEFAULT)
        targets = self._migration_targets()
        assert targets, "parsed no migration targets — the table shape moved"
        # A bare-domain form of a host the pipeline does fetch is fine
        # (`oagkenya.go.ke` for `www.oagkenya.go.ke`); a DIFFERENT subdomain
        # is not, which is exactly what `newsite.` was.
        strays = {
            site: h
            for site, h in targets.items()
            if h not in fetched
            and not any(f == h or f.endswith("." + h) for f in fetched)
        }
        assert not strays, (
            "the auto-filed issue tells maintainers to migrate TO hosts "
            f"nothing in the seeding pipeline fetches: {strays}"
        )

    def test_treasury_is_pointed_at_the_host_the_pipeline_uses(self):
        guidance = self._guidance()
        treasury = [ln for ln in guidance.splitlines() if "| Treasury |" in ln]
        assert len(treasury) == 1, treasury
        old, new = treasury[0].split("|")[2:4]
        assert "newsite.treasury.go.ke" in old, old
        assert "www.treasury.go.ke" in new, new


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
