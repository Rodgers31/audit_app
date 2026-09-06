"""Layer 3 — who currently governs each county, from the Council of Governors.

WHY THIS EXISTS
---------------
The governor shown on a county page came from ``enhanced_county_data.json``,
typed in once and 377 days old. The frontend carried a SECOND hardcoded list
of its own (``lib/data/county-officials.ts``, with party and term), which is
what actually rendered. Two unsourced lists of the same 47 facts, neither able
to notice an election, a death or a court ruling.

Governors are not a figure this project can gate on plausibility — a name is
either right or wrong. So the only defence is reading it from the body that
publishes it: the Council of Governors, whose membership IS the 47 sitting
governors, at https://cog.go.ke/current-governors/.

READING IT
----------
Each governor is one block of markup pairing a name with a county::

    <div class="captions">
        <h3>H.E Benjamin Chesire Cheboi, EGH, EBS</h3>
        <p><strong>County:</strong> Baringo</p>
    </div>

Parsed as pairs inside a block rather than by document order. The page also
carries former governors under their own headings, and a slider that repeats
entries; pairing inside the block makes both harmless, and the gates below
catch it if that ever stops being true.

THE GATES
---------
1. All 47 counties, each exactly once. A page that lists 46 is a page that
   changed shape, not a country with 46 counties.
2. No name governing two counties — the failure mode of pairing by position
   rather than by block.
3. Names must look like names: honorifics and post-nominals stripped, at
   least two words left, no digits.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("seeding.extractors.cog_governors")

EXTRACTOR_ID = "cog_governors"

SOURCE_URL = "https://cog.go.ke/current-governors/"
PUBLISHER = "Council of Governors"

#: The 47, spelled as this project spells them.
from .knbs_census_population import KENYAN_COUNTIES  # noqa: E402  (single source)

#: One governor's block: the name in an <h3>, the county in the paragraph that
#: follows. ``.*?`` across the gap because the markup between them varies.
_ENTRY_RE = re.compile(
    r"<h3[^>]*>(?P<name>[^<]{4,120})</h3>.*?"
    r"<strong>\s*County\s*:\s*</strong>\s*(?P<county>[^<]{2,40})",
    re.I | re.S,
)

#: Honorifics and professional prefixes the Council prints before a name.
#: They stack — "Maj. (Rtd) Dr. Dhadho Gaddae Godhana" — and some are
#: qualifications rather than titles ("FCPA Ahmed Abdullahi"), which is why
#: they are stripped from the front as well as the back.
_HONORIFIC_RE = re.compile(
    r"^\s*(?:"
    r"H\.?\s*E\.?|HON\.?|DR\.?|PROF\.?|MR\.?|MRS\.?|MS\.?|ENG\.?|"
    r"AMB\.?|SEN\.?|GOV\.?|F?CPA|ARCH\.?|"
    r"MAJ\.?|COL\.?|GEN\.?|CAPT\.?|LT\.?|BRIG\.?|"
    r"\(\s*RTD\.?\s*\)|RTD\.?"
    r")\s*",
    re.I,
)

#: Post-nominal honours, with or without a comma before them. The Council
#: writes both "Cheboi, EGH, EBS" and "Natembeya MBS".
_POSTNOMINAL_RE = re.compile(
    r"(?:\s*,\s*|\s+)(?:EGH|CBS|EBS|MBS|MGH|OGW|HSC|PhD|MP|MCA|FCPA|CPA)\b"
    r"(?:[\s,]*(?:EGH|CBS|EBS|MBS|MGH|OGW|HSC|PhD|MP|MCA|FCPA|CPA)\b)*\s*$",
    re.I,
)

#: Labels that are section headings, not people.
_NOT_A_NAME = re.compile(
    r"governors?|deputy|council|county assembl|leadership|committee", re.I
)


class GovernorsError(Exception):
    """A parse that must be QUARANTINED, never published."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass
class Governors:
    by_county: Dict[str, str]
    checks: List[str] = field(default_factory=list)


def _county_key(label: str) -> str:
    key = re.sub(r"[^a-z]", "", (label or "").lower())
    # The Council writes "Nairobi City", as the census volume does.
    return "nairobi" if key == "nairobicity" else key


def clean_name(raw: str) -> Optional[str]:
    """A governor's name with honorifics and post-nominals removed.

    ``None`` when what is left cannot be a name — a section heading, a digit,
    or a single word.
    """
    name = re.sub(r"\s+", " ", (raw or "").replace("&#8217;", "'")).strip()
    name = _POSTNOMINAL_RE.sub("", name)
    # Honorifics can stack: "H.E HON. DR. ..."
    for _ in range(4):
        stripped = _HONORIFIC_RE.sub("", name)
        if stripped == name:
            break
        name = stripped
    name = name.strip(" ,.")
    if not name or any(ch.isdigit() for ch in name):
        return None
    if _NOT_A_NAME.search(name):
        return None
    if len(name.split()) < 2:
        return None
    return name


def parse_governors(html: str) -> Governors:
    """Extract county -> governor from the Council of Governors page."""
    by_county: Dict[str, str] = {}
    seen_names: Dict[str, str] = {}
    canonical = {_county_key(c): c for c in KENYAN_COUNTIES}

    for match in _ENTRY_RE.finditer(html or ""):
        county = canonical.get(_county_key(match.group("county")))
        if county is None:
            continue
        name = clean_name(match.group("name"))
        if name is None:
            continue
        if county in by_county:
            # The page repeats entries in a slider; the first wins, and a
            # DISAGREEING repeat is a parse that has gone wrong.
            if by_county[county] != name:
                raise GovernorsError(
                    "county_has_two_governors",
                    f"{county}: {by_county[county]!r} and {name!r}",
                )
            continue
        if name in seen_names and seen_names[name] != county:
            raise GovernorsError(
                "governor_of_two_counties",
                f"{name} appears for both {seen_names[name]} and {county} — "
                "names and counties are probably paired by position rather "
                "than within a block",
            )
        by_county[county] = name
        seen_names[name] = county

    if not by_county:
        raise GovernorsError(
            "no_governors_found",
            f"{SOURCE_URL} yielded no county/name pairs; the page's markup "
            "has probably changed",
        )

    missing = sorted(set(KENYAN_COUNTIES) - set(by_county))
    if missing:
        raise GovernorsError(
            "counties_missing",
            f"{len(missing)} of {len(KENYAN_COUNTIES)} not listed: "
            f"{', '.join(missing)}",
        )

    return Governors(
        by_county=by_county,
        checks=[
            f"all {len(KENYAN_COUNTIES)} counties listed exactly once",
            f"{len(set(by_county.values()))} distinct governors, one per county",
        ],
    )
