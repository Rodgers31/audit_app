"""Is the publisher ahead of us?

WHY THIS EXISTS
---------------
The freshness gates in ``staleness.py`` ask whether a table has MOVED and
whether a domain REACHED its publisher. Neither asks the question a reader
cares about: *has the publisher released something newer than what we show?*
The two came apart on the nightly of 2026-09-24, which printed::

    [OK] national_budget: completed | … | source=live
    [OK] revenue_by_source: completed | … | source=live

while the /budget execution panel was empty in production (#241) and KRA had
published FY 2025/26 revenue eleven weeks earlier (#243). Both domains had
reached a publisher. Neither held its current edition.

HOW
---
A fetcher that discovers editions records the newest one it saw
(``freshness.record_publisher_edition``) BEFORE it downloads or parses, and
the CLI stores it on the job as ``meta.publisher_edition``. Each rule below
compares that with the newest edition the database actually PUBLISHES — read
through the same function the API serves from, so "held" cannot mean a row
the page would refuse to show.

* publisher newer than held  -> FAIL
* nothing held at all        -> FAIL
* latest run recorded no edition (discovery failed, or the domain did not
  run)                        -> WARN. Absence of evidence is not currency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, List, Optional

from .staleness import FAIL, OK, WARN, Finding

_FY_START_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def fy_start_year(label: Optional[str]) -> Optional[int]:
    """2025 for "FY 2025/26", "FY2025/26", "FY 2025/2026"; None otherwise."""
    if not label:
        return None
    m = _FY_START_RE.search(label)
    return int(m.group(1)) if m else None


def _held_execution_fy(session) -> Optional[str]:
    from services.budget_execution import execution_by_sector

    return execution_by_sector(session)["fiscal_year"]


@dataclass(frozen=True)
class EditionRule:
    domain: str
    dataset: str
    label: str
    held: Callable[[object], Optional[str]]


EDITION_RULES: List[EditionRule] = [
    EditionRule(
        domain="national_budget",
        dataset="cob_ng_birr_annual",
        label="Execution by sector (COB annual NG-BIRR)",
        held=_held_execution_fy,
    ),
]


def _latest_job(session, domain: str):
    from models import IngestionJob

    return (
        session.query(IngestionJob)
        .filter(IngestionJob.domain == domain)
        .order_by(IngestionJob.started_at.desc(), IngestionJob.id.desc())
        .first()
    )


def check_publisher_editions(
    session, rules: Optional[List[EditionRule]] = None
) -> List[Finding]:
    findings: List[Finding] = []
    for rule in rules if rules is not None else EDITION_RULES:
        job = _latest_job(session, rule.domain)
        if job is None:
            findings.append(
                Finding(WARN, rule.label, f"no {rule.domain} run recorded")
            )
            continue
        seen = (job.meta or {}).get("publisher_edition")
        if not isinstance(seen, dict) or seen.get("dataset") != rule.dataset:
            findings.append(
                Finding(
                    WARN,
                    rule.label,
                    f"the latest {rule.domain} run (job {job.id}) did not record "
                    f"the publisher's newest {rule.dataset} edition — discovery "
                    "failed or never ran, so currency is UNKNOWN",
                )
            )
            continue
        published = seen.get("edition")
        pub_year = fy_start_year(published)
        held = rule.held(session)
        held_year = fy_start_year(held)
        where = f" ({seen.get('url')})" if seen.get("url") else ""
        if pub_year is None:
            findings.append(
                Finding(
                    WARN,
                    rule.label,
                    f"publisher edition {published!r} is not a fiscal year",
                )
            )
        elif held_year is None:
            findings.append(
                Finding(
                    FAIL,
                    rule.label,
                    f"publisher lists {published}{where}; we publish NO edition",
                )
            )
        elif pub_year > held_year:
            findings.append(
                Finding(
                    FAIL,
                    rule.label,
                    f"publisher lists {published}{where}; newest we publish is "
                    f"{held}",
                )
            )
        else:
            findings.append(
                Finding(
                    OK,
                    rule.label,
                    f"publishing {held}; publisher's newest is {published}",
                )
            )
    return findings


__all__ = [
    "EDITION_RULES",
    "EditionRule",
    "check_publisher_editions",
    "fy_start_year",
]
