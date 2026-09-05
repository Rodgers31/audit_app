"""Layer 3 — county population from the 2019 Census, Volume I, Table 2.2.

WHY THIS EXISTS
---------------
Every county population on the site came from ``enhanced_county_data.json``,
a file whose own metadata calls its figures "realistic estimates". The
population field happens NOT to be estimated — it is the real Census 2019
count — but nothing in the pipeline could show that, because the file cites
no document and no page. A true number with no provenance is still a number
a reader has to take on trust.

The domain's other route was no better. ``real_data_fetcher`` advertises
"Fetch real population data from KNBS County Statistical Abstracts", discovers
the documents, and then ignores them::

    # For MVP: Use known 2019 census data as baseline
    census_2019_data = self._get_2019_census_data()

— a dict typed into the source file. And the one live attempt that did read a
KNBS PDF wrote twelve rows, all of them attributed to Samburu, with years
130, 135, 220, 232, 252, 335, 396, 399, 531, 621 and 897. The publication gate
withheld them, which is the only reason none of it reached a reader.

THE SOURCE
----------
2019 Kenya Population and Housing Census, Volume I: Population by County and
Sub-County (KNBS, November 2019), Table 2.2 "Distribution of Population by Sex
and County" — one page carrying all 47 counties and the national total.

READING IT
----------
The PDF letter-spaces its digits, so the text layer is ambiguous::

    Tana River………….… 1 58,550 1 57,391 2 3 15,943

"2 3 15,943" is intersex 2 and total 315,943, but it reads equally well as 23
and 15,943, and no amount of string splitting can tell which. The columns are
recovered from geometry instead: fragments of one number sit at most 0.3pt
apart, while the nearest two columns are 12.4pt apart — a 40x margin, measured
across all 48 rows of the table rather than assumed. ``COLUMN_GAP_PT`` sits in
that gap.

THE GATES
---------
Nothing is emitted unless the table proves itself. The first two are the
table's own arithmetic, which a slipped column cannot satisfy by accident:

1. Every row reconciles: male + female + intersex == total.
2. The 47 county totals sum to the national total printed above them.
3. Exactly 47 counties, each name resolving to a county this project knows.
4. Each total sits inside a plausible band.
5. Text integrity — a page whose glyphs decode to ``(cid:nn)`` is rejected
   rather than published as mojibake, as the other extractors do.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger("seeding.extractors.knbs_census_population")

EXTRACTOR_ID = "knbs_census_population"

#: The census this table reports. Not "the current year": these are counted
#: people on a census night, and labelling them with today's year would claim
#: a count nobody has taken.
CENSUS_YEAR = 2019

#: Printed on the same page, and what the county totals must sum to.
PUBLISHED_NATIONAL_TOTAL = 47_564_296

#: How the table names itself.
TABLE_MARKER = "distribution of population by sex and county"

#: Fragments closer than this belong to one number; anything wider is a column
#: boundary. Measured, not guessed: max intra-number gap 0.3pt, min
#: inter-column gap 12.4pt, over all 48 rows of Table 2.2.
COLUMN_GAP_PT = 4.0

#: A county cannot have fewer people than Lamu (143,920) or more than Nairobi
#: (4,397,073) by an order of magnitude. Catches a units error or a column
#: slip that still happens to reconcile.
PLAUSIBLE_COUNTY_TOTAL = (10_000, 20_000_000)

#: Above this share of undecodable glyphs the page is a rendering artefact,
#: not text. Same threshold the OAG extractors use.
MAX_CID_RATIO = 0.02

_CID_RE = re.compile(r"\(cid:\d+\)")

#: Leaders, spaces and stray dots the renderer scatters through both the names
#: and the numbers ("Laikipia…………… 2 …59..,440").
_NOISE_RE = re.compile(r"[\s.,…·]+")

#: As Table 2.2 prints them -> the canonical county name this project uses.
#: Only the ones that actually differ; everything else matches on its own.
_COUNTY_ALIASES: Dict[str, str] = {
    "taitataveta": "Taita Taveta",
    "tharakanithi": "Tharaka Nithi",
    "elgeyomarakwet": "Elgeyo Marakwet",
    # The census names the city; the county is "Nairobi".
    "nairobicity": "Nairobi",
    "muranga": "Murang'a",
}

#: The 47, so a missing or invented row is caught by name and not just by
#: count. Spelled as this project spells them.
KENYAN_COUNTIES: Tuple[str, ...] = (
    "Baringo", "Bomet", "Bungoma", "Busia", "Elgeyo Marakwet", "Embu",
    "Garissa", "Homa Bay", "Isiolo", "Kajiado", "Kakamega", "Kericho",
    "Kiambu", "Kilifi", "Kirinyaga", "Kisii", "Kisumu", "Kitui", "Kwale",
    "Laikipia", "Lamu", "Machakos", "Makueni", "Mandera", "Marsabit", "Meru",
    "Migori", "Mombasa", "Murang'a", "Nairobi", "Nakuru", "Nandi", "Narok",
    "Nyamira", "Nyandarua", "Nyeri", "Samburu", "Siaya", "Taita Taveta",
    "Tana River", "Tharaka Nithi", "Trans Nzoia", "Turkana", "Uasin Gishu",
    "Vihiga", "Wajir", "West Pokot",
)

_CANONICAL_BY_KEY = {
    _NOISE_RE.sub("", name).lower().replace("'", ""): name for name in KENYAN_COUNTIES
}


class CensusPopulationError(Exception):
    """A parse that must be QUARANTINED, never published.

    Carries a machine-readable ``reason`` so the caller can record why nothing
    was emitted instead of logging prose nobody gates on.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class CountyPopulation:
    county: str  # canonical, e.g. "Taita Taveta"
    male: int
    female: int
    intersex: int
    total: int
    page: int


@dataclass
class CensusPopulation:
    counties: List[CountyPopulation]
    national_total: int
    page: int
    checks: List[str] = field(default_factory=list)


def cid_ratio(text: str) -> float:
    """Share of the text that is undecodable ``(cid:nn)`` glyph references."""
    if not text:
        return 0.0
    return sum(len(m.group(0)) for m in _CID_RE.finditer(text)) / len(text)


def _to_int(fragments: Sequence[str]) -> Optional[int]:
    """Join one column's fragments into the integer they spell."""
    digits = _NOISE_RE.sub("", "".join(fragments))
    if not digits or not digits.isdigit():
        return None
    return int(digits)


def group_by_column(words: Sequence[dict], gap: float = COLUMN_GAP_PT) -> List[List[dict]]:
    """Split one line's words into columns wherever the gap widens.

    Geometry, not string splitting: the text layer cannot say whether
    "2 3 15,943" is (2, 315943) or (23, 15943), but the glyph positions can.
    """
    columns: List[List[dict]] = []
    for word in sorted(words, key=lambda w: w["x0"]):
        if columns and word["x0"] - columns[-1][-1]["x1"] <= gap:
            columns[-1].append(word)
        else:
            columns.append([word])
    return columns


def split_label(line: Sequence[dict]) -> Tuple[List[dict], List[dict]]:
    """Separate a row's label from its numbers, at the first digit.

    Position alone cannot do this. The dot leaders after a long county name
    overrun the first numeric column — Laikipia's trail ends at x=205 while
    its male figure starts at x=203 — so a purely geometric split swallows the
    number into the name, and the row is silently dropped. That is what the
    "counties do not sum to national" gate caught: Laikipia, Nakuru, Narok and
    Kajiado, exactly the four longest names on the page, and exactly the
    4,956,475 people missing from the total.

    A digit is unambiguous where a coordinate is not: no county name contains
    one, and every figure begins with one.
    """
    for index, word in enumerate(sorted(line, key=lambda w: w["x0"])):
        if any(ch.isdigit() for ch in word["text"]):
            ordered = sorted(line, key=lambda w: w["x0"])
            return ordered[:index], ordered[index:]
    return list(line), []


def canonical_county(raw: str) -> Optional[str]:
    """The county this label names, or None if it names none.

    Strips the dot leaders and the letter-spacing, so "Taita/Taveta……..….…"
    and "Elgeyo/Marakwet" land on the names this project uses.
    """
    key = _NOISE_RE.sub("", raw or "").lower().replace("/", "").replace("-", "")
    key = key.replace("'", "").replace("’", "")
    if key in _COUNTY_ALIASES:
        return _COUNTY_ALIASES[key]
    return _CANONICAL_BY_KEY.get(key)


def _lines(words: Iterable[dict], tolerance: float = 3.0) -> List[List[dict]]:
    """Group words into visual lines by their vertical position."""
    buckets: Dict[int, List[dict]] = {}
    for word in words:
        key = int(round(float(word["top"]) / tolerance))
        buckets.setdefault(key, []).append(word)
    return [buckets[k] for k in sorted(buckets)]


def parse_population_table(words: Iterable[dict], page: int) -> CensusPopulation:
    """Read Table 2.2 out of one page's positioned words.

    ``words`` are pdfplumber ``extract_words()`` dicts (``text``, ``x0``,
    ``x1``, ``top``), which is all this needs — the caller owns the PDF.
    """
    rows: List[CountyPopulation] = []
    national: Optional[int] = None
    national_parts: Optional[Tuple[int, int, int]] = None

    for line in _lines(list(words)):
        label_words, numeric_words = split_label(line)
        if not label_words or not numeric_words:
            continue
        columns = group_by_column(numeric_words)
        if len(columns) != 4:  # male, female, intersex, total
            continue
        label = " ".join(w["text"] for w in label_words)
        numbers = [_to_int([w["text"] for w in col]) for col in columns]
        if any(n is None for n in numbers):
            continue
        male, female, intersex, total = numbers  # type: ignore[misc]

        key = _NOISE_RE.sub("", label).lower()
        if key.startswith("kenya"):
            national = total
            national_parts = (male, female, intersex)
            continue

        county = canonical_county(label)
        if county is None:
            continue
        rows.append(
            CountyPopulation(
                county=county,
                male=male,
                female=female,
                intersex=intersex,
                total=total,
                page=page,
            )
        )

    return _gate(rows, national, national_parts, page)


def _gate(
    rows: List[CountyPopulation],
    national: Optional[int],
    national_parts: Optional[Tuple[int, int, int]],
    page: int,
) -> CensusPopulation:
    """Refuse anything the table does not prove."""
    checks: List[str] = []

    if not rows:
        raise CensusPopulationError(
            "no_counties_extracted", f"page {page} yielded no county rows"
        )

    # Gate 1 — the row's own arithmetic. A column read from the wrong place
    # cannot satisfy this by accident.
    for row in rows:
        if row.male + row.female + row.intersex != row.total:
            raise CensusPopulationError(
                "row_does_not_reconcile",
                f"{row.county}: {row.male} + {row.female} + {row.intersex} "
                f"!= {row.total}",
            )
    checks.append(f"male+female+intersex==total for all {len(rows)} counties")

    if national_parts is not None and national is not None:
        if sum(national_parts) != national:
            raise CensusPopulationError(
                "national_row_does_not_reconcile",
                f"{national_parts} does not sum to {national}",
            )
        checks.append("the national row reconciles too")

    # Gate 2 — the counties must add up to the national total printed above
    # them. This is the check that catches a missing or duplicated row.
    if national is None:
        raise CensusPopulationError(
            "national_total_not_found",
            "the table's Kenya row was not read, so nothing can be checked "
            "against it",
        )
    if national != PUBLISHED_NATIONAL_TOTAL:
        raise CensusPopulationError(
            "national_total_unexpected",
            f"table says {national:,}, the published 2019 count is "
            f"{PUBLISHED_NATIONAL_TOTAL:,}",
        )
    county_sum = sum(r.total for r in rows)
    if county_sum != national:
        raise CensusPopulationError(
            "counties_do_not_sum_to_national",
            f"{len(rows)} counties sum to {county_sum:,}, national total is "
            f"{national:,} (difference {county_sum - national:+,})",
        )
    checks.append(f"the {len(rows)} county totals sum to the national {national:,}")

    # Gate 3 — all 47, none twice.
    names = [r.county for r in rows]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise CensusPopulationError(
            "duplicate_county", f"read more than once: {', '.join(duplicates)}"
        )
    missing = sorted(set(KENYAN_COUNTIES) - set(names))
    if missing:
        raise CensusPopulationError(
            "counties_missing",
            f"{len(missing)} of 47 not read: {', '.join(missing)}",
        )
    checks.append("all 47 counties present, each exactly once")

    # Gate 4 — plausibility, which catches a units error that still reconciles.
    low, high = PLAUSIBLE_COUNTY_TOTAL
    for row in rows:
        if not (low <= row.total <= high):
            raise CensusPopulationError(
                "population_outside_plausible_band",
                f"{row.county}: {row.total:,} is outside [{low:,}, {high:,}]",
            )
    checks.append(f"every county total inside [{low:,}, {high:,}]")

    return CensusPopulation(
        counties=sorted(rows, key=lambda r: r.county),
        national_total=national,
        page=page,
        checks=checks,
    )


def find_population_table(pages: Sequence) -> int:
    """Index of the page carrying Table 2.2, or raise.

    ``pages`` are pdfplumber page objects. The table is found by what it calls
    itself rather than by a page number, because a reprint moves the page and
    a page number that silently points at the wrong table is exactly the
    failure the gates exist to prevent.
    """
    for index, page in enumerate(pages):
        text = page.extract_text() or ""
        if cid_ratio(text) > MAX_CID_RATIO:
            continue
        squashed = re.sub(r"\s+", " ", text).lower()
        if TABLE_MARKER in squashed and "mombasa" in squashed:
            return index
    raise CensusPopulationError(
        "population_table_not_found",
        f"no page carries '{TABLE_MARKER}' together with county rows",
    )


def extract_census_population(pdf) -> CensusPopulation:
    """Read the county populations out of an open pdfplumber document."""
    index = find_population_table(pdf.pages)
    page = pdf.pages[index]
    text = page.extract_text() or ""
    ratio = cid_ratio(text)
    if ratio > MAX_CID_RATIO:
        raise CensusPopulationError(
            "pdf_unreadable", f"page {index + 1} is {ratio:.0%} undecodable glyphs"
        )
    result = parse_population_table(page.extract_words(), page=index + 1)
    logger.info(
        "KNBS census: %d counties from page %d; %s",
        len(result.counties), result.page, "; ".join(result.checks),
    )
    return result
