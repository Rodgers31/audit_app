"""COB CBIRR stalled-projects parser, against verbatim extracts (#230).

Fixtures in ``tests/fixtures/cob_cbirr/`` are what pdfplumber and pdfium
returned for the real editions, unedited:

* FY2025/26 annual (August 2026), wpdmdl=16482
* FY2025/26 first quarter (November 2025), wpdmdl=16323
* FY2024/25 annual (August 2025), wpdmdl=16263

They were chosen for the layouts that break a naive parser, not for being
typical. Every expected figure below was read off the PDF page by hand; none
was copied from this parser's output.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from seeding.domains.stalled_projects import cob_parser as cp

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "cob_cbirr"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


ANNUAL = _load("fy2025_26_annual.json")
Q1 = _load("fy2025_26_q1.json")
FY2425 = _load("fy2024_25_annual.json")


def _table(fx: dict, county: str) -> dict:
    c = fx["counties"][county]
    return cp.parse_table(c["header"], [(p, r) for p, r in c["rows"]])


def _summary(fx: dict, county: str):
    c = fx["counties"][county]
    text = cp.clean(c["previous_page_text"] + " " + c["caption_page_text"])
    m = cp.SUMMARY_RE.search(text)
    return cp.parse_summary_sentence(text[m.start():]) if m else None


def _t26() -> dict:
    return cp.parse_table_2_6([(p, r) for p, r in ANNUAL["table_2_6"]["rows"]])


def _county(fx: dict, county: str, *, t26: bool = False) -> dict:
    parsed = _table(fx, county)
    summary = _summary(fx, county)
    t26_entry = _t26()["counties"].get(county) if t26 else None
    return {
        "table": parsed,
        "summary": summary,
        "rec": cp.reconcile(parsed["rows"], parsed["total"], summary, t26_entry),
    }


def _by_name(rows, fragment):
    return next(r for r in rows if fragment.lower() in (r["project_name"] or "").lower())


# --------------------------------------------------------------------------
# Numbers, units, names
# --------------------------------------------------------------------------


class TestCells:
    @pytest.mark.parametrize("cell", ["-", "", "–", "N/A", "Not provided", None])
    def test_missing_is_none_never_zero(self, cell):
        assert cp.parse_amount(cell, 1.0) == (None, "missing")

    @pytest.mark.parametrize("cell", ["Nil", "Not Paid"])
    def test_cob_saying_nothing_was_paid_is_zero(self, cell):
        # Garissa FY2025/26 prints "Nil"; Laikipia Q1 prints "Not Paid".
        assert cp.parse_amount(cell, 1.0) == (0.0, None)

    def test_malformed_number_is_refused_not_guessed(self):
        # Uasin Gishu FY2025/26, row 3, verbatim.
        assert cp.parse_amount("3,490.800.00", 1.0) == (None, "unparseable")

    def test_unit_comes_from_the_header(self):
        assert cp.unit_from_header("Estimated Value of the Project (Kshs.)") == 1.0
        assert cp.unit_from_header("Contract sum (Kshs. Million)") == 1e6
        assert cp.unit_from_header("Amount (Kshs.Mn)") == 1e6
        assert cp.unit_from_header("Amount Paid on the stalled project") is None

    def test_no_unit_means_no_figure(self):
        assert cp.parse_amount("1,000", None) == (None, "unit_not_stated")

    @pytest.mark.parametrize(
        "printed,county",
        [
            ("Kakemega", "Kakamega"),  # FY2025/26 9-month caption, sic
            ("Elegyo-Marakwet", "Elgeyo Marakwet"),  # Q1 chapter heading, sic
            ("Elgeyo", "Elgeyo Marakwet"),  # Q1 caption
            ("Nairobi City", "Nairobi"),
            ("Tharaka-Nithi", "Tharaka Nithi"),
            ("Murang’a", "Murang'a"),
            ("Kisii", "Kisii"),
            ("Kitui", "Kitui"),
        ],
    )
    def test_county_names_normalise_to_the_47(self, printed, county):
        assert cp.normalise_county(printed) == county

    @pytest.mark.parametrize("printed", ["analyses the number of", "Total", "Ki", ""])
    def test_anything_looser_is_refused(self, printed):
        assert cp.normalise_county(printed) is None

    def test_percent_cell_holding_prose_is_flagged_not_coerced(self):
        # Nairobi FY2025/26 row 19, verbatim.
        assert cp.parse_percent("75% from the previous contract") == (None, "not_a_percentage")
        assert cp.parse_percent("46%") == (46.0, None)  # Meru FY2025/26


# --------------------------------------------------------------------------
# FY2025/26 annual
# --------------------------------------------------------------------------


class TestFy2526Annual:
    def test_baringo_follows_the_table_overleaf_and_reconciles(self):
        c = _county(ANNUAL, "Baringo", t26=True)
        rows = c["table"]["rows"]
        assert len(rows) == 23
        assert {r["source_page"] for r in rows} == {70, 71}
        # COB's TOTALS row: 163,319,185 and 83,693,749.
        assert c["table"]["total"]["estimated_value_kes"] == 163_319_185
        assert sum(r["estimated_value_kes"] for r in rows) == 163_319_185
        marigut = _by_name(rows, "Marigut")
        assert marigut["cells"]["Amount Paid on the stalled project (Kshs.)"] == "-"
        assert marigut["amount_paid_kes"] is None  # "-" is not 0
        # The paid total covers only the rows that print a figure.
        assert c["rec"]["amount_paid_rows"] < 23
        assert c["rec"]["status"] == "agrees_with_gaps"

    def test_kericho_has_no_number_column_and_a_unitless_paid_column(self):
        c = _county(ANNUAL, "Kericho", t26=True)
        rows = c["table"]["rows"]
        assert "row_no" not in c["table"]["layout"]["columns"]
        assert [r["row_no"] for r in rows] == [None] * 6
        assert rows[0]["project_name"] == "Kiboybei Water Supply"
        # "Amount Paid on the stalled project" names no unit; its siblings say
        # (Kshs.). The inherited unit is flagged, and COB's own sentence
        # (Kshs.95.39 million) then confirms it.
        assert "amount_paid:unit_from_sibling_column" in rows[0]["flags"]
        assert c["rec"]["amount_paid_kes_sum"] == pytest.approx(95_394_674.22)
        assert c["rec"]["status"] == "agrees"

    def test_nandi_contract_layout_has_no_amount_paid(self):
        c = _county(ANNUAL, "Nandi", t26=True)
        rows = c["table"]["rows"]
        assert len(rows) == 6
        assert "amount_paid" not in c["table"]["layout"]["columns"]
        assert all("amount_paid_kes" not in r for r in rows)
        # "Cumulative project expenditure" is not "amount paid", and is not
        # published as it.
        assert "cumulative_expenditure" in c["table"]["layout"]["columns"]
        assert rows[0]["group"] == "County Funded Projects"
        assert c["rec"]["estimated_value_kes_sum"] == 23_002_616
        paid_checks = [ch for ch in c["rec"]["checks"] if ch["check"] == "amount_paid_kes"]
        assert all(ch["agrees"] is None for ch in paid_checks)

    def test_kakamega_text_and_table_disagree_and_both_are_kept(self):
        c = _county(ANNUAL, "Kakamega", t26=True)
        rows = c["table"]["rows"]
        assert len(rows) == 10
        assert c["summary"]["count"] == 26
        assert c["summary"]["value_kes"] == pytest.approx(848.95e6)
        # COB's TOTALS row (241,277,062) is rows 1-9 (241,277,061), give or
        # take a shilling: it leaves out its own row 10 (2,242,295).
        rows_1_to_9 = sum(r["estimated_value_kes"] for r in rows if r["row_no"] != "10")
        assert c["table"]["total"]["estimated_value_kes"] == 241_277_062
        assert abs(c["table"]["total"]["estimated_value_kes"] - rows_1_to_9) <= 1
        assert _by_name(rows, "toilets and renovation")["estimated_value_kes"] == 2_242_295
        # "Kshs.218.98 has already been paid" — no unit printed.
        assert c["summary"]["paid_kes"] == pytest.approx(218.98e6)
        assert "paid_unit_not_printed_inherited_from_value" in c["summary"]["flags"]
        failing = {(ch["check"], ch["cob_source"]) for ch in c["rec"]["checks"] if ch["agrees"] is False}
        assert ("count", "county summary sentence") in failing
        assert ("count", "Table 2.6") in failing
        assert ("estimated_value_kes", "table total row") in failing
        assert c["rec"]["status"] == "disagrees"

    def test_lamu_header_out_of_step_with_its_data(self):
        c = _county(ANNUAL, "Lamu", t26=True)
        rows = c["table"]["rows"]
        assert len(rows) == 3
        # The percentage column holds the reason text.
        assert all(r["completion_pct"] is None for r in rows)
        assert all("completion_pct:not_a_percentage" in r["flags"] for r in rows)
        # Value and paid still sum to COB's sentence.
        assert c["rec"]["estimated_value_kes_sum"] == pytest.approx(366_132_994)
        by = {(ch["check"], ch["cob_source"]): ch["agrees"] for ch in c["rec"]["checks"]}
        assert by[("estimated_value_kes", "county summary sentence")] is True
        assert by[("count", "county summary sentence")] is False  # 3 rows, "4"

    def test_trans_nzoia_unit_conflict_is_named(self):
        c = _county(ANNUAL, "Trans Nzoia", t26=True)
        row = c["table"]["rows"][0]
        assert row["cells"]["Estimated Value (Kshs.)"] == "874"
        assert row["cells"]["Amount Paid (Kshs.)"] == "94.52"
        assert c["table"]["total"]["cells"]["Amount Paid (Kshs.)"] == "794.52"
        # Header says Kshs.; Table 2.6 says 874.00 million.
        assert c["rec"]["unit_conflicts"] == ["estimated_value_kes"]

    def test_samburu_totals_row_has_no_label(self):
        c = _county(ANNUAL, "Samburu", t26=True)
        assert len(c["table"]["rows"]) == 1
        assert c["table"]["total"]["estimated_value_kes"] == 116_951_010
        assert c["rec"]["status"] == "agrees"

    def test_nairobi_row_with_no_project_name_is_kept(self):
        c = _county(ANNUAL, "Nairobi", t26=True)
        rows = c["table"]["rows"]
        assert len(rows) == 57
        row41 = next(r for r in rows if r["row_no"] == "41")
        assert row41["project_name"] is None
        assert "project_name_blank" in row41["flags"]
        assert row41["estimated_value_kes"] == 13_995_406
        by = {(ch["check"], ch["cob_source"]): ch["agrees"] for ch in c["rec"]["checks"]}
        assert by[("count", "Table 2.6")] is True

    def test_uasin_gishu_malformed_value_is_a_gap(self):
        c = _county(ANNUAL, "Uasin Gishu", t26=True)
        bad = next(r for r in c["table"]["rows"] if "3,490.800.00" in r["cells"].values())
        assert bad["estimated_value_kes"] is None
        assert "estimated_value:unparseable" in bad["flags"]
        assert c["rec"]["estimated_value_rows"] == 3
        assert c["rec"]["status"] == "agrees_with_gaps"

    def test_kilifi_skips_row_four_and_says_ten(self):
        c = _county(ANNUAL, "Kilifi", t26=True)
        assert [r["row_no"] for r in c["table"]["rows"]] == ["1", "2", "3", "5", "6", "7", "8", "9", "10"]
        by = {(ch["check"], ch["cob_source"]): ch["agrees"] for ch in c["rec"]["checks"]}
        assert by[("count", "Table 2.6")] is False
        assert by[("estimated_value_kes", "Table 2.6")] is True

    def test_isiolo_na_is_missing(self):
        rows = _table(ANNUAL, "Isiolo")["rows"]
        cherab = _by_name(rows, "Cherab")
        assert cherab["cells"]["Amount Paid (Kshs.)"] == "N/A"
        assert cherab["amount_paid_kes"] is None


class TestTable26:
    def test_every_county_and_the_total(self):
        t = _t26()
        assert len(t["counties"]) == 47
        assert t["total"]["count"] == 189
        assert t["total"]["value_kes"] == pytest.approx(10_508.01e6)
        assert t["total"]["paid_kes"] == pytest.approx(4_206.15e6)

    def test_dash_is_missing_not_zero(self):
        bomet = _t26()["counties"]["Bomet"]
        assert bomet["printed"]["count"] == "-"
        assert (bomet["count"], bomet["value_kes"], bomet["paid_kes"]) == (None, None, None)

    def test_trans_nzoia_blank_count_kept_blank(self):
        tn = _t26()["counties"]["Trans Nzoia"]
        assert tn["count"] is None
        assert tn["value_kes"] == pytest.approx(874e6)

    def test_siaya_paid_more_than_value_is_published_as_printed(self):
        siaya = _t26()["counties"]["Siaya"]
        assert siaya["value_kes"] == pytest.approx(1.88e6)
        assert siaya["paid_kes"] == pytest.approx(3.72e6)


class TestAttribution:
    def test_isiolo_key_issue_is_not_filed_under_kajiado(self):
        """p.217 opens with Isiolo's recap ("The County has 7 stalled
        development projects worth Kshs.1.77 billion") and then starts
        Kajiado's chapter. By page, the sentence was Kajiado's."""
        b = ANNUAL["isiolo_kajiado_boundary"]
        doc = cp.Document(b["texts"])
        chapters = cp.find_chapters(doc)
        start, _ = chapters["Kajiado"]
        recap = doc.text.index("7 stalled development projects")
        assert recap < start
        assert doc.page_of(start) == 2  # the second page given, i.e. p.217

    def test_statement_that_a_county_reported_nothing_is_found(self):
        text = cp.clean(ANNUAL["vihiga_statement_page"]["text"])
        hits = [m.group(0) for m in cp.STATEMENT_RE.finditer(text) if "stalled" in m.group(0).lower()]
        assert any("did not report on stalled projects as of 30 June,2026" in h for h in hits)

    def test_list_of_tables_captions_are_dropped(self):
        """FY2024/25's list of tables uses dash leaders, not dots, so the
        caption regex matches it; only chapter position can tell."""
        toc_text = next(iter(FY2425["toc_pages"].values()))
        body = FY2425["elgeyo_body_page"]["text"]
        doc = cp.Document([toc_text, "3.5 County Government of Elgeyo Marakwet 3.5.1 Overview", body])
        caps = cp.find_captions(doc)
        assert any(c["page"] == 1 for c in caps), "the TOC caption is matched"
        kept = cp.body_captions(caps, cp.find_chapters(doc))
        assert kept and all(c["page"] == 3 for c in kept)


class TestSummarySentences:
    @pytest.mark.parametrize(
        "sentence,count,value,paid",
        [
            # Kitui FY2024/25 p.259 — comma inside the date.
            ("The County reported 14 stalled development projects as of 30 June, 2025, with an "
             "estimated value of Kshs.999.45 million, of which Kshs.476.92 million has been spent "
             "towards the projects, as shown in the Table 3.218.",
             14, 999.45e6, 476.92e6),
            # Siaya FY2025/26 p.758 — paid more than the value, as printed.
            ("The County reported 1 stalled development project as of 30 June 2026, with an estimated "
             "value of Kshs.1.88 million, of which Kshs.3.72 million has already been paid.",
             1, 1.88e6, 3.72e6),
            # Siaya Q1 FY2025/26 p.534 — no paid clause at all.
            ("The County reported three stalled development projects as of 30 September 2025, with an "
             "estimated value of Kshs.46.8 million. The projects are", 3, 46.8e6, None),
        ],
    )
    def test_sentence_forms(self, sentence, count, value, paid):
        s = cp.parse_summary_sentence(sentence)
        assert s["count"] == count
        assert s["value_kes"] == pytest.approx(value)
        assert s["paid_kes"] == (pytest.approx(paid) if paid is not None else None)

    def test_allocated_is_not_paid(self):
        # Machakos FY2024/25, verbatim.
        s = cp.parse_summary_sentence(
            "The County reported 54 stalled development projects as of 30 June, 2025, with an "
            "estimated value of Kshs.1.13 billion, of which Kshs.314.26 million has been "
            "allocated in the budget."
        )
        assert s["paid_kes"] is None
        assert "second_amount_described_as_other" in s["flags"]

    def test_spent_is_flagged_not_silently_called_paid(self):
        s = cp.parse_summary_sentence(
            "The County reported 14 stalled development projects as of 30 June, 2025, with an "
            "estimated value of Kshs.999.45 million, of which Kshs.476.92 million has been spent "
            "towards the projects, as shown in the Table 3.218."
        )
        assert "second_amount_described_as_spent" in s["flags"]

    def test_tolerance_follows_the_printed_precision(self):
        s = cp.parse_summary_sentence(
            "The County reported 20 stalled development projects as of 30 September 2025, with an "
            "estimated value of Kshs.321 million, of which Kshs.95.3 has already been paid."
        )
        # "321 million" is +/- 1M; "95.3" is +/- 0.1M (Kericho Q1 FY2025/26).
        assert s["value_tolerance_kes"] == pytest.approx(1e6 + 1)
        assert s["paid_tolerance_kes"] == pytest.approx(0.1e6 + 1)


class TestCaptionVariants:
    @pytest.mark.parametrize(
        "caption,county,assembly",
        [
            ("Table 3.11: Baringo County Stalled Projects as of 30 June 2026", "Baringo", False),
            ("Table 3.11: Baringo County List of Stalled Projects as of 30th June 2025", "Baringo", False),
            ("Table 3.218: Kitui County, List of Stalled Projects as of 30 June 2025", "Kitui", False),
            ("Table 3.193: Kisii County Assembly Stalled Projects as of 30 September 2025", "Kisii", True),
            ("Table 3.163: Kakemega County Stalled Projects as of 31st March 2026", "Kakamega", False),
        ],
    )
    def test_every_printed_form_is_a_caption(self, caption, county, assembly):
        """Verbatim captions from the three editions (FY2024/25 p.73 and
        p.259, Q1 FY2025/26 p.265, and the 9-month edition)."""
        caps = cp.find_captions(cp.Document([caption + " No Project Name"]))
        assert len(caps) == 1
        assert caps[0]["county"] == county
        assert (caps[0]["reported_by"] == cp.REPORTED_BY_ASSEMBLY) is assembly


class TestNationalSentence:
    def test_189_projects(self):
        text = cp.clean(" ".join(ANNUAL["table_2_6"]["page_texts"]))
        m = cp.NATIONAL_RE.search(text)
        assert m and m.group("n") == "189"
        assert m.group("v") == "10.51" and m.group("p") == "4.21"


# --------------------------------------------------------------------------
# FY2025/26 first quarter
# --------------------------------------------------------------------------


class TestQ1:
    def test_garissa_column_shift_is_detected(self):
        c = _county(Q1, "Garissa")
        rows = c["table"]["rows"]
        # "NA" under Estimated Value; the values are printed under "Amount
        # Paid" (46,563,340 for the Health Headquarters, as in every other
        # edition), and the paid figures under "Outstanding Balance".
        assert {r["cells"]["Estimated Value of the Project (Kshs.)"] for r in rows} == {"NA"}
        assert _by_name(rows, "Health Head")["amount_paid_kes"] == 46_563_340
        # So the "paid" column sums to the sentence's VALUE, Kshs.283.54M.
        shifted = {s["field"]: s["matches"] for s in c["rec"]["column_shift"]}
        assert shifted["amount_paid_kes"] == [("county summary sentence", "estimated_value_kes")]

    def test_baringo_counts_numbered_rows_as_cob_does(self):
        c = _county(Q1, "Baringo")
        rows = c["table"]["rows"]
        assert len(rows) == 21
        assert sum("unnumbered_row" in r["flags"] for r in rows) == 5
        assert c["rec"]["rows_numbered"] == 16
        count = next(ch for ch in c["rec"]["checks"] if ch["check"] == "count")
        assert (count["rows"], count["cob"], count["agrees"]) == (16, 16, True)

    def test_laikipia_not_paid_is_a_stated_zero(self):
        c = _county(Q1, "Laikipia")
        assert [r["amount_paid_kes"] for r in c["table"]["rows"]] == [0.0] * 4
        # COB's sentence says Kshs.1.11 paid; its table says Not Paid.
        paid = next(ch for ch in c["rec"]["checks"] if ch["check"] == "amount_paid_kes")
        assert paid["agrees"] is False

    def test_kiambu_reported_by_the_county_assembly(self):
        s = _summary(Q1, "Kiambu")
        assert s["reported_by"] == cp.REPORTED_BY_ASSEMBLY
        assert s["paid_kes"] == 0.0  # "of which no amount has been paid"
        assert s["count"] == 1


# --------------------------------------------------------------------------
# FY2024/25 annual
# --------------------------------------------------------------------------


class TestFy2425:
    def test_turkana_misaligned_table_publishes_nothing_and_keeps_every_line(self):
        c = _county(FY2425, "Turkana")
        assert c["table"]["rows"] == []
        assert c["table"]["total"] is None
        assert c["table"]["layout"]["misaligned"] is True
        kept = [s for s in c["table"]["skipped"] if s["why"] == "header_and_data_misaligned"]
        assert len(kept) == 4
        assert any("Kataboi" in json.dumps(s["cells"]) for s in kept)

    def test_garissa_sentence_quotes_the_outstanding_balance(self):
        c = _county(FY2425, "Garissa")
        # The table's own total agrees with its rows...
        total = c["table"]["total"]
        assert total["estimated_value_kes"] == pytest.approx(283_540_196.60)
        assert c["rec"]["estimated_value_kes_sum"] == pytest.approx(283_540_196.60)
        # ...and COB's sentence says 244.88 million, which is the table's
        # "Outstanding Balance" total (244,888,144.60).
        assert c["summary"]["value_kes"] == pytest.approx(244.88e6)
        assert total["outstanding_balance_kes"] == pytest.approx(244_888_144.60)
        assert c["rec"]["column_shift"] == []  # our columns are right; COB's sentence is not

    def test_kwale_total_row_leaves_out_rows(self):
        c = _county(FY2425, "Kwale")
        assert c["table"]["total"]["estimated_value_kes"] == pytest.approx(465_273_525.60)
        assert c["rec"]["estimated_value_kes_sum"] == pytest.approx(480_430_358.60)
        assert c["rec"]["status"] == "disagrees"


class TestAdversarialFindings:
    """Inputs an adversarial pass used to make the first version of this
    parser over-confident. Not seen in the three editions yet; each is one
    typesetting or wording change away."""

    def test_whole_billion_sentence_is_not_a_billion_wide_tolerance(self):
        s = cp.parse_summary_sentence(
            "The County reported 2 stalled development projects as of 30 June 2026, with an "
            "estimated value of Kshs.1 billion, of which Kshs.300 million has already been paid."
        )
        rows = [{"estimated_value_kes": 0.5e9, "amount_paid_kes": 300e6, "flags": []},
                {"estimated_value_kes": 1.0, "amount_paid_kes": 0.0, "flags": []}]
        assert cp.reconcile(rows, None, s, None)["status"] == "disagrees"

    @pytest.mark.parametrize("clause", ["has not been paid", "is yet to be paid", "remains unpaid"])
    def test_an_unpaid_amount_is_not_read_as_paid(self, clause):
        s = cp.parse_summary_sentence(
            "The County reported 23 stalled development projects as of 30 June 2026, with an "
            f"estimated value of Kshs.163.32 million, of which Kshs.83.69 million {clause}."
        )
        assert s["paid_kes"] is None

    @pytest.mark.parametrize("header", ["Amount Paid (Kshs. '000)", "Amount Paid (Kshs. in thousands)"])
    def test_thousands_header(self, header):
        assert cp.unit_from_header(header) == 1e3

    @pytest.mark.parametrize("cell", ["1000000\n500000", "1 2"])
    def test_two_figures_in_one_cell_are_refused(self, cell):
        assert cp.parse_amount(cell, 1.0) == (None, "unparseable")

    def test_space_after_a_thousands_comma_is_still_read(self):
        # Laikipia Q1 FY2025/26, verbatim.
        assert cp.parse_amount("1, 053,976.40", 1.0) == (1_053_976.40, None)

    @pytest.mark.parametrize("header", ["Balance to be paid (Kshs.)", "Amount not yet paid (Kshs.)", "Percentage Paid"])
    def test_headers_that_say_paid_but_mean_something_else(self, header):
        cols = cp.map_columns(["No", "Project Name", header, "Amount Paid (Kshs.)"])["columns"]
        assert cols.get("amount_paid") == 3

    def test_a_name_only_row_in_an_unnumbered_table_is_a_row_not_a_heading(self):
        header = ["Project Name", "Project Location", "Estimated Value of the Project (Kshs.)"]
        t = cp.parse_table(header, [(1, ["Kapsuser Market Shed", "", ""]),
                                    (1, ["Donor Funded Projects", "", ""]),
                                    (1, ["Bureti Fire Station", "Kapkatet", "8,248,375.00"])])
        assert [r["project_name"] for r in t["rows"]] == ["Kapsuser Market Shed", "Bureti Fire Station"]
        assert t["rows"][1]["group"] == "Donor Funded Projects"

    def test_a_row_narrower_than_its_header_is_flagged(self):
        header = ["No", "Project Name", "Project Location", "Estimated Value (Kshs.)"]
        t = cp.parse_table(header, [(1, ["1", "Hall", "1,000"])])
        assert "row_width_differs_from_header" in t["rows"][0]["flags"]

    @pytest.mark.parametrize("printed", ["East Pokot", "Nyandira"])
    def test_near_misses_are_not_filed_under_a_neighbour(self, printed):
        assert cp.normalise_county(printed) is None

    def test_count_only_agreement_with_no_values_is_not_plain_agrees(self):
        s = cp.parse_summary_sentence(
            "The County reported 1 stalled development project as of 30 June 2026, with an "
            "estimated value of Kshs.5.00 million, of which Kshs.1.00 million has already been paid."
        )
        rows = [{"estimated_value_kes": None, "amount_paid_kes": None, "flags": []}]
        assert cp.reconcile(rows, None, s, None)["status"] != "agrees"

    def test_true_is_not_a_figure(self):
        rows = [{"estimated_value_kes": True, "flags": []}]
        assert cp.reconcile(rows, None, None, None)["estimated_value_kes_sum"] is None
