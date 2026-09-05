"""Decide which OAG documents are county audits BEFORE downloading them.

WHY THIS EXISTS
---------------
The audits domain fetches every candidate and only then hands it to a parser,
so a document the parser will refuse is downloaded first and refused second.
That is what blew the 600s domain budget on 2026-09-05::

    VOLUME II    6.6 MB, 232 pages, extract  26s
    VOLUME I     7.6 MB, 469 pages, extract  40s
    COVID funds  262.5 MB

The two volumes that carry all 47 counties cost 66s between them. The budget
went on a 262MB thematic audit — "UTILIZATION OF COVID-19 FUNDS BY COUNTY
GOVERNMENTS" — which the parser then refused for naming no auditee. The run
aborted with nothing written.

A county financial audit names itself in its title, so candidacy can be
decided from the URL alone, for free, before a byte is transferred.

DELIBERATELY CONSERVATIVE
-------------------------
This rejects only what it can positively identify as NOT a county financial
audit. Anything it cannot classify is kept and passed to the parser, whose
gates are the real decision — a filter that silently drops a real report would
lose audit findings, which is far worse than spending a download on a
document the parser then refuses.
"""

from __future__ import annotations

import re
from typing import List, Sequence, Tuple

#: A single-entity report: "County-Assembly-of-Homa-Bay-2021-2022.pdf",
#: "County-Executive-of-Kwale-...", "County-Government-of-...".
_SINGLE_ENTITY_RE = re.compile(
    r"county[-_\s]*(assembly|executive|government)[-_\s]*of[-_\s]", re.I
)

#: A consolidated volume: "REPORT-OF-THE-AUDITOR-GENERAL-FOR-THE-COUNTY-
#: GOVERNMENTS-FOR-THE-YEAR-2020-2021-_VOLUME-II-COUNTY-ASSEMBLIES.pdf".
_CONSOLIDATED_RE = re.compile(
    r"auditor[-_\s]*general[-_\s]*for[-_\s]*the[-_\s]*county[-_\s]*governments", re.I
)

#: Titles that are positively something else. OAG publishes thematic and
#: performance audits under the same media library, and they mention "county"
#: without being county financial audits.
_NOT_A_COUNTY_AUDIT = (
    (re.compile(r"utilization[-_\s]*of[-_\s]*covid", re.I), "thematic_covid_audit"),
    (re.compile(r"emergency[-_\s]*medical|medical[-_\s]*care", re.I), "performance_audit"),
    (re.compile(r"popular[-_\s]*report", re.I), "popular_report"),
    (re.compile(r"special[-_\s]*audit", re.I), "special_audit"),
    (re.compile(r"terms[-_\s]*of[-_\s]*reference", re.I), "not_an_audit_report"),
)


def classify_county_audit_candidate(url: str) -> Tuple[bool, str]:
    """``(keep, reason)`` for one candidate URL, decided from its name only.

    Order matters: a recognised county-audit shape wins over the
    not-an-audit patterns, so a genuine report whose title happens to contain
    one of those words is still kept.
    """
    name = (url or "").rsplit("/", 1)[-1]
    if _CONSOLIDATED_RE.search(name):
        return True, "consolidated_volume"
    if _SINGLE_ENTITY_RE.search(name):
        return True, "single_entity_report"
    for pattern, why in _NOT_A_COUNTY_AUDIT:
        if pattern.search(name):
            return False, why
    # Unclassifiable: keep it. The parser's gates are the real decision, and
    # dropping a real report here would lose findings silently.
    return True, "unclassified_kept"


def split_county_audit_candidates(
    urls: Sequence[str],
) -> Tuple[List[str], List[Tuple[str, str]]]:
    """``(keep, [(url, why_rejected), ...])``."""
    keep: List[str] = []
    rejected: List[Tuple[str, str]] = []
    for url in urls:
        ok, why = classify_county_audit_candidate(url)
        (keep if ok else rejected).append(url if ok else (url, why))
    return keep, rejected
