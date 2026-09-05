"""The CBIRR county table must be read whole.

The consolidated table in the FY2025/26 County Budget Implementation Review
Report runs across two pages: 39 counties on page 61, the remaining 8 and the
Total row on page 62. Only page 61 could ever be selected — ranking requires
30+ county rows and the continuation has 8 — so the parse covered 39 of the 47
counties and said nothing, with the Total row that would have exposed it
sitting on the page nobody read.

Two things were wrong at once, which is why the shortfall survived:

* the Recurrent and Development categories could not resolve their expenditure
  column ("Expenditure (Kshs.Million) Rec" matches neither "actual expenditure
  rec" nor "recurrent expenditure"), so both fell back to a legacy path that
  found only 25 counties;
* nothing counted the rows or added them up.
"""

from decimal import Decimal

import pytest

from seeding.pdf_parsers import (
    CountyTableIncomplete,
    ExtractedTable,
    _check_county_coverage,
    _county_key,
    find_column_index,
    stitch_table_continuation,
)

COUNTIES = [
    "Baringo", "Bomet", "Bungoma", "Busia", "Elgeyo Marakwet", "Embu",
    "Garissa", "Homa Bay", "Isiolo", "Kajiado", "Kakamega", "Kericho",
    "Kiambu", "Kilifi", "Kirinyaga", "Kisii", "Kisumu", "Kitui", "Kwale",
    "Laikipia", "Lamu", "Machakos", "Makueni", "Mandera", "Marsabit", "Meru",
    "Migori", "Mombasa", "Murang'a", "Nairobi", "Nakuru", "Nandi", "Narok",
    "Nyamira", "Nyandarua", "Nyeri", "Samburu", "Siaya", "Taita Taveta",
    "Tana River", "Tharaka Nithi", "Trans Nzoia", "Turkana", "Uasin Gishu",
    "Vihiga", "Wajir", "West Pokot",
]

HEADERS = [
    "County",
    "Budget Estimates (Kshs.Million Rec",
    "Budget Estimates (Kshs.Million Dev",
    "Budget Estimates (Kshs.Million Total",
    "Expenditure (Kshs.Million) Rec",
    "Expenditure (Kshs.Million) Dev",
    "Expenditure (Kshs.Million) Total",
]


def table(page, names, *, headers=HEADERS, index=0):
    return ExtractedTable(
        page_number=page,
        table_index=index,
        headers=list(headers),
        rows=[[n, "1", "2", "3", "1", "1", "2"] for n in names],
        bbox=(0.0, 0.0, 100.0, 100.0),
    )


class TestTheExpenditureColumnResolves:
    """The FY2025/26 header wording, which no synonym matched."""

    @pytest.mark.parametrize(
        "synonyms,expected",
        [
            ([["expenditure", "rec"]], 4),
            ([["expenditure", "dev"]], 5),
            ([["expenditure", "total"]], 6),
        ],
    )
    def test_the_sub_column_wording_is_matched(self, synonyms, expected):
        assert find_column_index(HEADERS, synonyms) == expected

    def test_the_old_synonyms_alone_would_still_miss_it(self):
        """Why the categories fell back to the legacy path.

        The cell says "Expenditure … Rec" — no "actual", and "Rec" not
        "Recurrent".
        """
        assert (
            find_column_index(
                HEADERS,
                [["actual", "expenditure", "rec"], ["recurrent", "expenditure"]],
            )
            is None
        )


class TestStitching:
    def test_a_continuation_page_is_joined(self):
        base = table(61, COUNTIES[:39])
        cont = table(62, COUNTIES[39:])

        joined = stitch_table_continuation(base, [base, cont], COUNTIES)

        assert len(joined.rows) == 47
        assert joined.page_number == 61  # provenance stays with the base page

    def test_a_table_with_nothing_new_is_not_joined(self):
        base = table(61, COUNTIES[:39])
        repeat = table(62, COUNTIES[:39])

        assert stitch_table_continuation(base, [base, repeat], COUNTIES).rows == base.rows

    def test_a_county_is_never_added_twice(self):
        base = table(61, COUNTIES[:39])
        cont = table(62, COUNTIES[38:])  # overlaps on Siaya

        joined = stitch_table_continuation(base, [base, cont], COUNTIES)

        keys = [_county_key(r[0]) for r in joined.rows]
        assert len(keys) == len(set(keys)) == 47

    def test_a_table_of_a_different_shape_is_not_joined(self):
        """An unrelated table on the next page must not be absorbed."""
        base = table(61, COUNTIES[:39])
        other = ExtractedTable(
            page_number=62,
            table_index=0,
            headers=["County", "Budget (Kshs.)", "Expenditure (Kshs.)"],
            rows=[[n, "1", "2"] for n in COUNTIES[39:]],
            bbox=(0.0, 0.0, 100.0, 100.0),
        )

        assert stitch_table_continuation(base, [base, other], COUNTIES).rows == base.rows

    def test_a_table_whose_rows_are_not_counties_is_not_joined(self):
        base = table(61, COUNTIES[:39])
        other = table(62, ["Ministry of Health", "Ministry of Energy"])

        assert stitch_table_continuation(base, [base, other], COUNTIES).rows == base.rows

    def test_a_table_far_later_in_the_document_is_not_joined(self):
        """A continuation is adjacent; page 780 is a different report section."""
        base = table(61, COUNTIES[:39])
        far = table(780, COUNTIES[39:])

        assert stitch_table_continuation(base, [base, far], COUNTIES).rows == base.rows

    def test_an_earlier_adjacent_page_is_joined(self):
        """Which half is the "base" depends on which one has more rows.

        The budget table's continuation is the page after it (39 counties on
        61, 8 on 62). The own-source revenue table's is the page BEFORE (33 on
        56, 13 on 55) — only page 56 clears the 30-row ranking threshold, so
        the base is the later page and its continuation is earlier. A
        forward-only join left Nairobi and twelve others out.
        """
        base = table(56, COUNTIES[13:])
        earlier = table(55, COUNTIES[:13])

        joined = stitch_table_continuation(base, [earlier, base], COUNTIES)

        assert len(joined.rows) == 47

    def test_a_table_with_different_headers_is_not_joined(self):
        """What replaced the direction guard, and a stronger test.

        This report has several 10-column county tables. Requiring the
        continuation to REPEAT the headers — which a real one does — is what
        stops the own-source revenue table being welded to the budget table.
        """
        base = table(61, COUNTIES[:39])
        other_headers = list(HEADERS)
        other_headers[1] = "Target (Kshs.Million) Ordinary OSR"
        other = table(62, COUNTIES[39:], headers=other_headers)

        assert stitch_table_continuation(base, [base, other], COUNTIES).rows == base.rows


class TestCountyKey:
    @pytest.mark.parametrize(
        "printed,canonical",
        [
            ("Elgeyo -\nMarakwet", "Elgeyo Marakwet"),
            ("Taita-Tav-\neta", "Taita Taveta"),
            ("Murang’a", "Murang'a"),
            ("Thara-\nka-Nithi", "Tharaka Nithi"),
        ],
    )
    def test_the_cbirr_spellings_reduce_to_ours(self, printed, canonical):
        """The report hyphenates across lines and uses a curly apostrophe."""
        assert _county_key(printed) == _county_key(canonical)

    def test_two_different_counties_do_not_collide(self):
        assert _county_key("Kisii") != _county_key("Kisumu")


def _records(names, allocated=Decimal("100")):
    return [
        {"county": n, "category": "Total", "allocated": allocated} for n in names
    ]


class TestCoverageGate:
    def test_a_complete_table_that_adds_up_passes(self):
        rows = _records(COUNTIES)
        printed = ["Total", "", "", str(Decimal("100") * 47)]

        _check_county_coverage(rows, printed, "x.pdf", 3)

    def test_a_missing_county_is_refused_and_named(self):
        """39 rows look exactly like 47 unless something counts them."""
        rows = _records(COUNTIES[:39])

        with pytest.raises(CountyTableIncomplete) as e:
            _check_county_coverage(rows, ["Total", "", "", "3900"], "x.pdf", 3)
        assert "Tana River" in str(e.value)
        assert "8 of 47" in str(e.value)

    def test_rows_that_do_not_sum_to_the_printed_total_are_refused(self):
        """Catches a row read from the wrong column, which a headcount cannot."""
        rows = _records(COUNTIES)

        with pytest.raises(CountyTableIncomplete) as e:
            _check_county_coverage(rows, ["Total", "", "", "398974.59"], "x.pdf", 3)
        assert "prints" in str(e.value)

    def test_the_check_reads_the_column_the_rows_came_from(self):
        """The Recurrent sub-total is not the budget total.

        Comparing against "the first big-looking cell" failed an exact parse:
        633,303.87 against the row's Recurrent figure of 398,974.59.
        """
        rows = _records(COUNTIES, allocated=Decimal("633303.87") / 47)
        printed = ["Total", "398974.59", "234329.28", "633303.87"]

        _check_county_coverage(rows, printed, "x.pdf", 3)

    def test_rounding_across_47_rows_is_allowed(self):
        rows = _records(COUNTIES)
        printed = ["Total", "", "", str(Decimal("100") * 47 - Decimal("2"))]

        _check_county_coverage(rows, printed, "x.pdf", 3)

    def test_a_drift_the_size_of_the_smallest_county_is_not(self):
        """Lamu reported KSh 4,988.65m — the tolerance must sit well below it."""
        rows = _records(COUNTIES, allocated=Decimal("10000"))
        printed = ["Total", "", "", str(Decimal("10000") * 47 - Decimal("4988.65"))]

        with pytest.raises(CountyTableIncomplete):
            _check_county_coverage(rows, printed, "x.pdf", 3)

    def test_a_table_with_no_total_row_passes_the_count_but_warns(self):
        """Absence of the anchor is not a parse failure, but it is worth saying."""
        _check_county_coverage(_records(COUNTIES), None, "x.pdf", 3)


class TestTheParserOnAWholeTable:
    """Drives ``parse()`` against a table shaped like the real one.

    The tests above check the pieces with the synonyms passed in by hand,
    which cannot tell whether the PARSER's own synonym list resolves the
    FY2025/26 wording — the thing that was actually wrong. This one can:
    remove ["expenditure", "rec"] from the parser and Recurrent disappears
    from the output.
    """

    FULL_HEADERS = [
        "County",
        "Budget Estimates (Kshs.Million Rec",
        "Budget Estimates (Kshs.Million Dev",
        "Budget Estimates (Kshs.Million Total",
        "Expenditure (Kshs.Million) Rec",
        "Expenditure (Kshs.Million) Dev",
        "Expenditure (Kshs.Million) Total",
        "Absorption Rate(%) Rec",
        "Absorption Rate(%) Dev",
        "Absorption Rate(%) Total",
    ]

    def _row(self, name):
        return [name, "60", "40", "100", "30", "20", "50", "50", "50", "50"]

    def _tables(self):
        """39 counties on one page, 8 and the Total row on the next."""
        first = ExtractedTable(
            page_number=61, table_index=0, headers=list(self.FULL_HEADERS),
            rows=[self._row(n) for n in COUNTIES[:39]],
            bbox=(0.0, 0.0, 100.0, 100.0),
        )
        second = ExtractedTable(
            page_number=62, table_index=0, headers=list(self.FULL_HEADERS),
            rows=[self._row(n) for n in COUNTIES[39:]]
            + [["Total", "2820", "1880", "4700", "1410", "940", "2350", "50", "50", "50"]],
            bbox=(0.0, 0.0, 100.0, 100.0),
        )
        return [first, second]

    def _parse(self, monkeypatch, tables):
        from pathlib import Path

        from seeding import pdf_parsers

        monkeypatch.setattr(pdf_parsers, "extract_all_tables", lambda _p: tables)
        return pdf_parsers.CoBQuarterlyReportParser(Path("cbirr.pdf")).parse()

    def test_all_three_categories_come_from_the_consolidated_table(self, monkeypatch):
        records = self._parse(monkeypatch, self._tables())
        categories = {r["category"] for r in records}

        assert categories == {"Total", "Recurrent", "Development"}

    def test_all_47_counties_are_read(self, monkeypatch):
        records = self._parse(monkeypatch, self._tables())
        totals = [r for r in records if r["category"] == "Total"]

        assert len(totals) == 47
        assert len(records) == 141

    def test_a_missing_continuation_page_is_refused(self, monkeypatch):
        """What the shortfall would look like now: loud, not silent."""
        tables = self._tables()[:1]  # page 61 only, no continuation

        with pytest.raises(CountyTableIncomplete) as e:
            self._parse(monkeypatch, tables)
        assert "West Pokot" in str(e.value)


class TestOwnSourceRevenue:
    """Table 2.1 — what each county raises itself.

    Not the county's budget: 47 counties collected KSh 53.9B against budgets
    of KSh 633.3B in the first nine months of FY 2025/26. The figure this
    replaces was 0.85 x a modelled budget, published as "Revenue Collected" —
    about ten times what counties actually collect.
    """

    OSR_HEADERS = [
        "County",
        "Target (Kshs.Million) Ordinary\nOSR",
        "Target (Kshs.Million) FIF/ AIA",
        "Target (Kshs.Million) Total OSR",
        "Actual Realised (Kshs.Million) Ordinary\nOSR",
        "Actual Realised (Kshs.Million) FIF/AIA",
        "Actual Realised (Kshs.Million) Total OSR",
        "Performance (%) Ordinary\nOSR",
        "Performance (%) FIF/AIA",
        "Performance (%) Total OSR",
    ]

    def _row(self, name):
        # target 100 total, realised 50 total
        return [name, "60", "40", "100", "30", "20", "50", "50", "50", "50"]

    def _tables(self, first_names, second_names, *, total_row=True):
        first = ExtractedTable(
            page_number=55, table_index=0, headers=list(self.OSR_HEADERS),
            rows=[self._row(n) for n in first_names],
            bbox=(0.0, 0.0, 100.0, 100.0),
        )
        rows = [self._row(n) for n in second_names]
        if total_row:
            n = len(first_names) + len(second_names)
            rows.append(
                ["Total", str(60 * n), str(40 * n), str(100 * n),
                 str(30 * n), str(20 * n), str(50 * n), "50", "50", "50"]
            )
        second = ExtractedTable(
            page_number=56, table_index=0, headers=list(self.OSR_HEADERS),
            rows=rows, bbox=(0.0, 0.0, 100.0, 100.0),
        )
        return [first, second]

    def _parse(self, monkeypatch, tables):
        """Drive the OSR extraction alone.

        ``self.tables`` is populated by ``parse()``, not the constructor, so a
        direct call needs it set — patching extract_all_tables is not enough.
        """
        from pathlib import Path

        from seeding import pdf_parsers

        parser = pdf_parsers.CoBQuarterlyReportParser(Path("cbirr.pdf"))
        parser.tables = tables
        return parser._extract_own_source_revenue()

    def test_all_47_counties_are_read_across_both_pages(self, monkeypatch):
        """13 counties on page 55, 34 on page 56 — only the second clears the
        30-row ranking threshold, so the continuation is the EARLIER page."""
        records = self._parse(
            monkeypatch, self._tables(COUNTIES[:13], COUNTIES[13:])
        )

        assert len(records) == 47
        assert {r["category"] for r in records} == {"Own Source Revenue"}

    def test_target_is_allocated_and_realised_is_absorbed(self, monkeypatch):
        """The same shape the budget rows use, so nothing downstream needs a
        special case — and the API reads the REALISED figure."""
        records = self._parse(
            monkeypatch, self._tables(COUNTIES[:13], COUNTIES[13:])
        )
        row = next(r for r in records if r["county"] == "Baringo")

        assert row["allocated"] == Decimal("100")  # Target, Total OSR column
        assert row["absorbed"] == Decimal("50")  # Actual Realised, Total OSR

    def test_nairobi_city_resolves_to_nairobi(self, monkeypatch):
        """The table names the capital "Nairobi City".

        Emitted verbatim, the writer slugified it to "nairobi-city-county",
        matched no county, and dropped the row with an error — so Nairobi, the
        largest own-source collector in the country, had no figure.
        """
        names = [c for c in COUNTIES if c != "Nairobi"]
        records = self._parse(
            monkeypatch, self._tables(names[:13], names[13:] + ["Nairobi City"])
        )

        assert "Nairobi" in {r["county"] for r in records}
        assert "Nairobi City" not in {r["county"] for r in records}

    def test_a_missing_county_is_refused(self, monkeypatch):
        from seeding.pdf_parsers import CountyTableIncomplete

        with pytest.raises(CountyTableIncomplete) as e:
            self._parse(monkeypatch, self._tables(COUNTIES[:13], COUNTIES[13:46]))
        assert "West Pokot" in str(e.value)

    def test_rows_that_do_not_sum_to_the_printed_total_are_refused(
        self, monkeypatch
    ):
        from seeding.pdf_parsers import CountyTableIncomplete

        tables = self._tables(COUNTIES[:13], COUNTIES[13:])
        # Move the printed Total far from the sum of the rows.
        tables[1].rows[-1][3] = "999999"

        with pytest.raises(CountyTableIncomplete):
            self._parse(monkeypatch, tables)

    def test_a_report_with_no_osr_table_yields_nothing(self, monkeypatch):
        """Absence is not a failure — an older vintage may not carry it."""
        plain = ExtractedTable(
            page_number=10, table_index=0,
            headers=["County", "Something", "Else"],
            rows=[[c, "1", "2"] for c in COUNTIES],
            bbox=(0.0, 0.0, 100.0, 100.0),
        )

        assert self._parse(monkeypatch, [plain]) == []


class TestTheApiReadsTheRealisedFigure:
    @staticmethod
    def _line(category, allocated, actual):
        from types import SimpleNamespace

        return SimpleNamespace(
            category=category, allocated_amount=allocated, actual_spent=actual
        )

    def test_it_reads_the_own_source_revenue_row(self):
        import main

        lines = [
            self._line("Total", 9_542_030_000, 4_092_380_000),
            self._line("Own Source Revenue", 1_000_000_000, 421_000_000),
        ]

        assert main.county_own_source_revenue(lines) == 421_000_000

    def test_it_does_not_read_the_budget_row(self):
        """The budget is not revenue, and confusing them is how a county's
        own collection came to be reported as 85% of its budget."""
        import main

        lines = [self._line("Total", 9_542_030_000, 4_092_380_000)]

        assert main.county_own_source_revenue(lines) is None

    def test_a_county_with_no_osr_row_is_absent_not_zero(self):
        import main

        result = main.county_own_source_revenue([])

        assert result is None
        assert result != 0

    def test_a_published_zero_is_kept(self):
        import main

        lines = [self._line("Own Source Revenue", 1_000_000, 0)]

        assert main.county_own_source_revenue(lines) == 0.0
