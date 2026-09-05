"""Gates on the 2019 Census county-population extractor.

Every gate gets a test that makes it FIRE. A gate only ever seen to pass is
not a gate, it is a comment — and these figures are the denominator of every
per-capita figure on the site, so a slipped column would be a published
falsehood about how much each Kenyan's county spends on them.

The table this reads (Volume I, Table 2.2) carries its own proof: each row's
male + female + intersex equals its total, and the 47 county totals sum to the
national count printed above them. A parse that grabbed the wrong column
cannot satisfy either by accident, which is why they are the first two gates.
"""

import pytest

from seeding.extractors.knbs_census_population import (
    COLUMN_GAP_PT,
    KENYAN_COUNTIES,
    PUBLISHED_NATIONAL_TOTAL,
    CensusPopulationError,
    canonical_county,
    find_population_table,
    group_by_column,
    parse_population_table,
    split_label,
)

# The real column origins from the source PDF, so the tests exercise the same
# geometry the extractor was measured against.
_COL_X = {"male": 203.0, "female": 267.0, "intersex": 355.0, "total": 384.0}
_CHAR_W = 5.0


def word(text: str, x0: float, top: float) -> dict:
    return {"text": text, "x0": x0, "x1": x0 + len(text) * _CHAR_W, "top": top}


def number_words(value: int, x0: float, top: float) -> list:
    """A figure as the PDF renders it: first digit split off from the rest.

    "1,208,333" is laid down as "1" then ",208,333" a hair's breadth later —
    0.3pt, well inside COLUMN_GAP_PT — which is why the columns have to be
    recovered from geometry and not from whitespace.
    """
    text = f"{value:,}"
    head, tail = text[0], text[1:]
    words = [word(head, x0, top)]
    if tail:
        words.append(word(tail, x0 + _CHAR_W + 0.3, top))
    return words


def row_words(
    label: str,
    male: int,
    female: int,
    intersex: int,
    total: int,
    top: float,
    leader_overrun: bool = False,
) -> list:
    """One table row, with the dot leaders the renderer draws after the name."""
    # A long name's leaders run PAST the first numeric column's origin, which
    # is the real quirk that dropped four counties.
    leader_end = _COL_X["male"] + 2 if leader_overrun else _COL_X["male"] - 20
    name = word(label + "…" * 8, 84.0, top)
    name["x1"] = leader_end
    words = [name]
    for key, value in (
        ("male", male), ("female", female), ("intersex", intersex), ("total", total)
    ):
        words.extend(number_words(value, _COL_X[key], top))
    return words


def table(
    overrides: dict | None = None,
    national: int | None = PUBLISHED_NATIONAL_TOTAL,
    counties: tuple = KENYAN_COUNTIES,
    leader_overrun_for: str | None = None,
) -> list:
    """A whole Table 2.2 whose rows and total agree by construction.

    Every county gets an equal share of the published national count and the
    first county absorbs the remainder, so the happy path satisfies the sum
    gate without embedding 47 literals a reader would have to check.
    """
    share = PUBLISHED_NATIONAL_TOTAL // len(counties)
    totals = {name: share for name in counties}
    totals[counties[0]] += PUBLISHED_NATIONAL_TOTAL - share * len(counties)
    totals.update(overrides or {})

    words = []
    top = 100.0
    if national is not None:
        # male + female + intersex must reconcile here too.
        words.extend(row_words("Kenya", national - 3, 2, 1, national, top))
        top += 13.0
    for name in counties:
        total = totals[name]
        intersex = 3
        male = (total - intersex) // 2
        female = total - intersex - male
        words.extend(
            row_words(
                name, male, female, intersex, total, top,
                leader_overrun=(name == leader_overrun_for),
            )
        )
        top += 13.0
    return words


class TestHappyPath:
    def test_reads_all_47_counties(self):
        result = parse_population_table(table(), page=17)

        assert len(result.counties) == 47
        assert result.national_total == PUBLISHED_NATIONAL_TOTAL
        assert sum(c.total for c in result.counties) == PUBLISHED_NATIONAL_TOTAL

    def test_records_every_check_it_ran(self):
        joined = " | ".join(parse_population_table(table(), page=17).checks)

        assert "male+female+intersex==total" in joined
        assert "sum to the national" in joined
        assert "all 47 counties present" in joined

    def test_a_leader_that_overruns_the_first_column_still_parses(self):
        """The regression the sum gate caught.

        Laikipia, Nakuru, Narok and Kajiado — the four longest names on the
        page — trail dots past where their male figure starts, so splitting
        the row by position alone swallowed the number into the name and
        dropped the row. Exactly 4,956,475 people went missing, and only the
        national-total check noticed.
        """
        result = parse_population_table(table(leader_overrun_for="Laikipia"), page=17)

        assert len(result.counties) == 47
        assert any(c.county == "Laikipia" for c in result.counties)


class TestGatesFire:
    def test_a_row_that_does_not_reconcile_is_refused(self):
        """male + female + intersex must equal the printed total."""
        words = table()
        # Break one row's arithmetic without touching its total.
        broken = [w for w in words if w["top"] != 113.0]
        broken.extend(row_words(KENYAN_COUNTIES[0], 1, 1, 1, 999_999, 113.0))

        with pytest.raises(CensusPopulationError) as e:
            parse_population_table(broken, page=17)
        assert e.value.reason == "row_does_not_reconcile"

    def test_counties_that_do_not_sum_to_the_national_total_are_refused(self):
        """One dropped row is invisible per-row and obvious in the sum."""
        with pytest.raises(CensusPopulationError) as e:
            parse_population_table(
                table(counties=KENYAN_COUNTIES[:46]), page=17
            )
        assert e.value.reason in {
            "counties_do_not_sum_to_national", "counties_missing"
        }

    def test_all_47_present_but_not_adding_up_is_refused(self):
        """The gate that actually caught the bug, on its own.

        Every county present, every row reconciling, one total wrong. Nothing
        per-row can see it — only the sum against the national count can, and
        this is the case that proves the check is load-bearing rather than
        shadowed by the missing-county gate.
        """
        share = PUBLISHED_NATIONAL_TOTAL // 47
        with pytest.raises(CensusPopulationError) as e:
            parse_population_table(
                table(overrides={KENYAN_COUNTIES[3]: share + 1_000}), page=17
            )
        assert e.value.reason == "counties_do_not_sum_to_national"
        assert "+1,000" in e.value.detail

    def test_a_missing_county_is_named(self):
        short = KENYAN_COUNTIES[:46]
        # Keep the sum right so the failure is specifically the absence.
        overrides = {short[0]: PUBLISHED_NATIONAL_TOTAL - sum(
            PUBLISHED_NATIONAL_TOTAL // len(short) for _ in short[1:]
        )}
        with pytest.raises(CensusPopulationError) as e:
            parse_population_table(
                table(counties=short, overrides=overrides), page=17
            )
        assert e.value.reason == "counties_missing"
        assert KENYAN_COUNTIES[46] in e.value.detail

    def test_a_county_read_twice_is_refused(self):
        doubled = KENYAN_COUNTIES + (KENYAN_COUNTIES[0],)
        with pytest.raises(CensusPopulationError) as e:
            parse_population_table(table(counties=doubled), page=17)
        assert e.value.reason in {"duplicate_county", "counties_do_not_sum_to_national"}

    def test_a_table_with_no_national_row_is_refused(self):
        """Without the anchor there is nothing to check the rows against."""
        with pytest.raises(CensusPopulationError) as e:
            parse_population_table(table(national=None), page=17)
        assert e.value.reason == "national_total_not_found"

    def test_a_national_total_that_is_not_the_published_one_is_refused(self):
        """Catches reading the wrong table, or the wrong census."""
        with pytest.raises(CensusPopulationError) as e:
            parse_population_table(table(national=38_610_097), page=17)
        assert e.value.reason == "national_total_unexpected"

    def test_an_implausible_county_total_is_refused(self):
        """A units error that still reconciles."""
        share = PUBLISHED_NATIONAL_TOTAL // 47
        overrides = {
            KENYAN_COUNTIES[0]: 999,
            KENYAN_COUNTIES[1]: share + (PUBLISHED_NATIONAL_TOTAL - share * 47) + share - 999,
        }
        with pytest.raises(CensusPopulationError) as e:
            parse_population_table(table(overrides=overrides), page=17)
        assert e.value.reason == "population_outside_plausible_band"

    def test_a_page_with_no_rows_is_refused(self):
        with pytest.raises(CensusPopulationError) as e:
            parse_population_table([word("nothing here", 84.0, 100.0)], page=3)
        assert e.value.reason == "no_counties_extracted"


class TestColumnGeometry:
    def test_fragments_of_one_number_stay_together(self):
        cols = group_by_column(number_words(1_208_333, 384.0, 100.0))

        assert len(cols) == 1

    def test_adjacent_columns_stay_apart(self):
        words = number_words(30, 355.0, 100.0) + number_words(1_208_333, 384.0, 100.0)

        assert len(group_by_column(words)) == 2

    def test_the_ambiguous_case_the_text_layer_cannot_resolve(self):
        """Tana River prints "2 3 15,943" — intersex 2, total 315,943.

        Read as text that is equally "23" and "15,943". Only the geometry says
        which, and getting it wrong would publish a county of 15,943 people.
        """
        words = number_words(2, 355.0, 100.0) + number_words(315_943, 384.0, 100.0)
        cols = group_by_column(words)

        assert [len(c) for c in cols] == [1, 2]

    def test_the_threshold_sits_between_the_two_measured_gaps(self):
        """0.3pt inside a number, 12.4pt between columns, measured over all
        48 rows. A threshold outside that window silently merges or splits."""
        assert 0.3 < COLUMN_GAP_PT < 12.4


class TestNameResolution:
    @pytest.mark.parametrize(
        "printed,expected",
        [
            ("Taita/Taveta……..….…", "Taita Taveta"),
            ("Elgeyo/Marakwet…….. ", "Elgeyo Marakwet"),
            ("Tharaka-Nithi…………", "Tharaka Nithi"),
            ("Murang'a………………. ", "Murang'a"),
            ("Nairobi City……..…….", "Nairobi"),
            ("Mombasa…………..…", "Mombasa"),
            ("Homa Bay…………….. ", "Homa Bay"),
        ],
    )
    def test_the_table_spelling_resolves_to_ours(self, printed, expected):
        assert canonical_county(printed) == expected

    def test_a_label_that_is_not_a_county_resolves_to_nothing(self):
        """Sub-county and section rows must not be mistaken for counties."""
        assert canonical_county("Changamwe") is None
        assert canonical_county("Total") is None

    def test_every_county_this_project_holds_is_listed(self):
        assert len(set(KENYAN_COUNTIES)) == 47


class TestLabelSplit:
    def test_the_split_is_at_the_first_digit(self):
        line = row_words("Nakuru", 1, 1, 1, 3, 100.0, leader_overrun=True)
        label, numbers = split_label(line)

        assert len(label) == 1
        assert "Nakuru" in label[0]["text"]
        assert all(any(ch.isdigit() for ch in w["text"]) for w in numbers[:1])

    def test_a_line_with_no_digits_yields_no_numbers(self):
        label, numbers = split_label([word("National/ County", 84.0, 100.0)])

        assert numbers == []


class TestFindingTheTable:
    class _Page:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    def test_the_table_is_found_by_what_it_calls_itself(self):
        pages = [
            self._Page("Foreword"),
            self._Page("Table 2. 2: Distribution of Population by Sex and County\nMombasa 1"),
        ]

        assert find_population_table(pages) == 1

    def test_a_document_without_the_table_is_refused(self):
        with pytest.raises(CensusPopulationError) as e:
            find_population_table([self._Page("Foreword"), self._Page("Annex")])
        assert e.value.reason == "population_table_not_found"

    def test_a_page_of_undecodable_glyphs_is_not_accepted_as_the_table(self):
        """Same rule the OAG extractors apply: mojibake is not text."""
        broken = "(cid:3)" * 200 + " distribution of population by sex and county mombasa"
        with pytest.raises(CensusPopulationError) as e:
            find_population_table([self._Page(broken)])
        assert e.value.reason == "population_table_not_found"
