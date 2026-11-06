"""Source glyph regressions; page doubles do not establish HTTP or PDF authority."""
import json
from pathlib import Path

import pytest

from seeding.extractors import oag_blue_book as bb


FIXTURE = json.loads((Path(__file__).parent / "fixtures/oag_tagged_table_2024_2025.json").read_text())


class SourcePage:
    def __init__(self, page):
        self.chars = page["chars"]
        self.bbox = page["bbox"]
        self.width = self.bbox[2] - self.bbox[0]
        self.height = self.bbox[3] - self.bbox[1]
        self.structure_tree = page["structure"]
        self.page_number = page["page_number"]
        self.raw_text = page["raw_text"]

    def extract_text(self):
        return self.raw_text


def page(number):
    return SourcePage(next(p for p in FIXTURE["pages"] if p["page_number"] == number))


@pytest.mark.parametrize("number,titles", [
    (266, [
        "10. Delayed Completion of Pediatric Emergency Centre and Burns Management Centre",
        "11. Inadequate Patients Beds at Mathari Hospital",
        "17. Proposed Establishment of a NEURpsychiatric National Teaching and Referral Hospital",
        "18. Procurement of the Healthcare Information Technology Digitization System",
    ]),
    (691, [
        "9. Delayed Completion of the Construction of National Employment Promotion Centre",
        "10. Delayed Completion of Construction of Occupational Safety and Health (OSH) Institute Phase 1",
        "11. Lack of Strategic Plan",
    ]),
])
def test_source_tagged_titles_keep_their_own_suffixes(number, titles):
    result = bb._page_text(page(number))
    lines = [" ".join(line.split()) for line in result.splitlines()]
    for title in titles:
        assert title in lines


def test_complete_source_parent_lists_and_layout_qualification():
    pages = []
    for local_page, physical in enumerate([265, 266], 1):
        qualifications = []
        text = bb._page_text(page(physical), qualifications=qualifications)
        pages.append(bb.PageText(local_page, text, "pdfplumber", qualifications))
    rows, rejected = bb.segment_chapter(pages, 1082, "State Department for Medical Services", 1, 2, 0)
    assert rejected == 0
    parent = next(r for r in rows if r.paragraph_no == 778)
    payload = bb.finding_to_extracted_json(parent, "2024/2025")
    assert [q["row_label"] for q in payload["layout_qualifications"]] == ["10.", "17."]
    assert all(q["pdf_page"] == 266 and q["requires_human_review"] is True
               and q["disposition"] == "qualified_embedded_text_visible_fidelity_unconfirmed"
               for q in payload["layout_qualifications"])
    assert len(rows) == 4
    assert all("layout_qualifications" not in bb.finding_to_extracted_json(r, "2024/2025")
               for r in rows if r.paragraph_no != 778)
    # Every historical row and subrow belongs to paragraph778, not a new finding.
    for source_page in [265, 266]:
        for line in bb._page_text(page(source_page)).splitlines():
            if line.startswith(tuple(f"{n}. " for n in range(1, 23))) or line.startswith("18."):
                assert " ".join(line.split()) in parent.finding_text
    assert parent.amounts == []


def test_second_source_parent_qualifies_both_overlapping_cells():
    qualifications = []
    text = bb._page_text(page(691), qualifications=qualifications)
    pages = [bb.PageText(1, text, "pdfplumber", qualifications)]
    clean = []
    rows, rejected = bb.segment_chapter(pages, 1184, "State Department for Labour and Skills Development", 1, 1, 0, clean_statements=clean)
    assert rejected == 0
    assert [r.paragraph_no for r in rows] == [2168, 2169]
    assert [r.paragraph_no for r in clean] == [2167]
    payload = bb.finding_to_extracted_json(rows[1], "2024/2025")
    assert [q["row_label"] for q in payload["layout_qualifications"]] == ["9.", "10."]
    for q in payload["layout_qualifications"]:
        assert q["cell_text"] in payload["finding_text"]
        assert q["requires_human_review"] is True
    assert "13. Incomplete Asset Register and Lack of Ownership Documents" in payload["finding_text"]
    assert payload["severity"] == "INFO"
    assert payload["amounts"] == []


def test_table_correction_preserves_original_glyphs_and_unrelated_prose():
    import copy
    source = page(266)
    before = copy.deepcopy(source.chars)
    result = bb._page_text(source)
    assert source.chars == before
    assert "Kshs.68,421,740,034" in result
    assert "Kshs.51,104,976,273 was unsupported." in result
    assert result.rstrip().endswith("253")


@pytest.mark.parametrize("bad", [None, {}, "table", True, 1, 1.0])
def test_malformed_structure_is_not_a_successful_repair(bad):
    source = page(266)
    source.structure_tree = bad
    with pytest.raises(ValueError, match="PDF structure"):
        bb._page_text(source)


def test_duplicate_marked_content_ownership_refuses():
    import copy
    source = page(266)
    source.structure_tree = copy.deepcopy(source.structure_tree)
    table = source.structure_tree[0]["children"][0]
    body = table["children"][1]["children"]
    body[6]["children"][1]["children"][0]["mcids"] = [13]
    with pytest.raises(ValueError, match="duplicate ownership"):
        bb._page_text(source)


@pytest.mark.parametrize("bad", [True, float("nan"), float("inf"), -float("inf"), "160"])
def test_nonfinite_or_wrong_type_marked_geometry_refuses(bad):
    import copy
    source = page(266)
    source.chars = copy.deepcopy(source.chars)
    target = next(c for c in source.chars if c["mcid"] == 13 and c["text"].strip())
    target["top"] = bad
    with pytest.raises(ValueError, match="glyph coordinates"):
        bb._page_text(source)


@pytest.mark.parametrize("bad", [True, 0, -1, "266", None, float("nan")])
def test_wrong_physical_page_identity_refuses(bad):
    source = page(266)
    source.page_number = bad
    with pytest.raises(ValueError, match="physical page"):
        bb._page_text(source)


def test_untagged_pages_keep_the_existing_geometry_reader():
    source = page(266)
    source.structure_tree = []
    assert bb._page_text(source) == source.raw_text


def test_single_line_cells_do_not_invoke_structure_reader():
    class PlainPage:
        chars = [{"text": "X", "mcid": 1, "x0": 1, "x1": 2, "top": 1, "bottom": 2}]
        def extract_text(self):
            return "X"
        @property
        def structure_tree(self):
            raise AssertionError("No overlapping marked cells")
    assert bb._page_text(PlainPage()) == "X"


@pytest.mark.parametrize("bad", [True, -1, "13", 13.0])
def test_wrong_type_marked_content_identity_refuses(bad):
    import copy
    source = page(266)
    source.chars = copy.deepcopy(source.chars)
    next(c for c in source.chars if c["mcid"] == 13)["mcid"] = bad
    with pytest.raises(ValueError, match="glyph identity"):
        bb._page_text(source)


def test_ocr_cannot_drop_an_embedded_table_visibility_hold(monkeypatch):
    import pdfplumber
    class Page:
        closed = False
        def close(self):
            self.closed = True
    source = Page()
    class PDF:
        pages = [source]
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
    def embedded(_, *, qualifications):
        qualifications.append({"cell_text": "Clipped embedded title", "requires_human_review": True})
        return "(cid:123)" * 20
    monkeypatch.setattr(pdfplumber, "open", lambda _: PDF())
    monkeypatch.setattr(bb, "_page_text", embedded)
    monkeypatch.setattr(bb, "_ocr_page", lambda *args: "A readable visible sentence, without the clipped embedded suffix.")
    result = bb.read_pages(Path("owned-page-double.pdf"), ocr_enabled=True)
    assert result[0].method == "rejected"
    assert result[0].layout_qualifications[0]["requires_human_review"] is True
    assert source.closed is True
