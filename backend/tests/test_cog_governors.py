"""Gates on the Council of Governors extractor.

The governor on a county page came from enhanced_county_data.json, typed in
once and 377 days old, and the frontend carried a second hardcoded list of its
own. Neither could notice an election.

A name cannot be gated on plausibility the way a figure can — it is either
right or wrong — so the gates are about completeness and pairing: all 47
counties exactly once, nobody governing two counties, and nothing that is
not a name.
"""

import pytest

from seeding.extractors.cog_governors import (
    KENYAN_COUNTIES,
    GovernorsError,
    clean_name,
    parse_governors,
)


def block(name: str, county: str) -> str:
    """One governor as the Council's page marks them up."""
    return (
        '<div class="captions">'
        f"<h3>{name}</h3>"
        f"<p><strong>County:</strong> {county}</p>"
        "</div>"
    )


def page(pairs) -> str:
    return "<html><body>" + "".join(block(n, c) for n, c in pairs) + "</body></html>"


def _synthetic(county: str) -> str:
    """A unique two-word name with no digits and no "governor" in it.

    Both matter: clean_name rejects section headings ("Current Governors") and
    anything containing a digit ("2022 Election Results"). A fixture that
    tripped either would be testing the guard, not the parse. Derived from the
    county so every name is distinct — the "one person, two counties" gate
    would otherwise fire on the happy path.
    """
    stem = "".join(ch for ch in county if ch.isalpha())
    return f"H.E {stem} Mwangi"


ALL_47 = [(_synthetic(c), c) for c in KENYAN_COUNTIES]


class TestHappyPath:
    def test_all_47_counties_are_read(self):
        result = parse_governors(page(ALL_47))

        assert len(result.by_county) == 47
        assert set(result.by_county) == set(KENYAN_COUNTIES)

    def test_the_name_is_paired_with_its_own_county(self):
        """Pairing by document order rather than within the block put each
        name against its neighbour's county."""
        pairs = [
            ("H.E Alice Achieng", c) if c == "Kisumu"
            else ("H.E Brian Barasa", c) if c == "Kakamega"
            else (n, c)
            for n, c in ALL_47
        ]
        result = parse_governors(page(pairs))

        assert result.by_county["Kisumu"] == "Alice Achieng"
        assert result.by_county["Kakamega"] == "Brian Barasa"

    def test_the_capital_is_matched_under_either_name(self):
        """The Council writes "Nairobi City", as the census volume does."""
        pairs = [(n, "Nairobi City" if c == "Nairobi" else c) for n, c in ALL_47]

        assert "Nairobi" in parse_governors(page(pairs)).by_county

    def test_it_records_the_checks_it_ran(self):
        joined = " | ".join(parse_governors(page(ALL_47)).checks)

        assert "47 counties listed exactly once" in joined
        assert "one per county" in joined


class TestNameCleaning:
    @pytest.mark.parametrize(
        "printed,expected",
        [
            ("H.E Benjamin Chesire Cheboi, EGH, EBS", "Benjamin Chesire Cheboi"),
            ("H.E Joshua Wakahora Irungu, EGH", "Joshua Wakahora Irungu"),
            # Post-nominals with no comma before them.
            ("H.E George Natembeya MBS", "George Natembeya"),
            # A qualification used as a prefix.
            ("H.E FCPA Ahmed Abdullahi", "Ahmed Abdullahi"),
            # Stacked honorifics.
            ("H.E Maj. (Rtd) Dr. Dhadho Gaddae Godhana", "Dhadho Gaddae Godhana"),
            ("H.E HON. STEPHEN KIPYEGO SANG, EGH", "STEPHEN KIPYEGO SANG"),
        ],
    )
    def test_honorifics_and_post_nominals_come_off(self, printed, expected):
        assert clean_name(printed) == expected

    @pytest.mark.parametrize(
        "label", ["Current Governors", "Deputy Governors", "2017 - 2022 Governors"]
    )
    def test_section_headings_are_not_names(self, label):
        """The page carries former governors under their own headings."""
        assert clean_name(label) is None

    def test_a_single_word_is_not_a_name(self):
        assert clean_name("H.E Sakaja") is None

    def test_anything_with_a_digit_is_not_a_name(self):
        assert clean_name("2022 Election Results") is None


class TestGatesFire:
    def test_a_missing_county_is_refused_and_named(self):
        with pytest.raises(GovernorsError) as e:
            parse_governors(page(ALL_47[:46]))

        assert e.value.reason == "counties_missing"
        assert KENYAN_COUNTIES[46] in e.value.detail

    def test_one_person_governing_two_counties_is_refused(self):
        """The signature of pairing names to counties by position."""
        pairs = [("H.E Same Person", c) for _, c in ALL_47[:2]] + ALL_47[2:]

        with pytest.raises(GovernorsError) as e:
            parse_governors(page(pairs))
        assert e.value.reason == "governor_of_two_counties"

    def test_a_county_listed_twice_with_different_names_is_refused(self):
        pairs = ALL_47 + [("H.E Someone Else", KENYAN_COUNTIES[0])]

        with pytest.raises(GovernorsError) as e:
            parse_governors(page(pairs))
        assert e.value.reason == "county_has_two_governors"

    def test_a_county_repeated_with_the_SAME_name_is_fine(self):
        """The page runs a slider that repeats entries."""
        pairs = ALL_47 + [ALL_47[0]]

        assert len(parse_governors(page(pairs)).by_county) == 47

    def test_a_page_whose_markup_changed_is_refused(self):
        with pytest.raises(GovernorsError) as e:
            parse_governors("<html><body><p>Our governors</p></body></html>")
        assert e.value.reason == "no_governors_found"

    def test_an_empty_page_is_refused(self):
        with pytest.raises(GovernorsError) as e:
            parse_governors("")
        assert e.value.reason == "no_governors_found"
