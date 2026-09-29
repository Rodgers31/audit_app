"""Source-shaped regression for OAG FY2024/25 Assemblies, PDF pp.239-242.

The fixture is pdfplumber ``extract_text()`` from the official PDF whose
SHA256 is aa72b0a512fe01ce8f40b9ed8597bd78657a9f441a8daf4963b07e661104d896.
It includes the complete paragraph 645 and the separate historical list.
"""

from pathlib import Path

from seeding.extractors.oag_blue_book import PageText, segment_chapter


FIXTURE = Path(__file__).parent / "fixtures/oag_nairobi_assembly_2024_2025_p239_242.txt"


def _source_pages():
    text = FIXTURE.read_text(encoding="utf-8").split("\f")
    assert len(text) == 4
    return [PageText(i, "", "pdfplumber") for i in range(1, 239)] + [
        PageText(i, body, "pdfplumber") for i, body in enumerate(text, 239)
    ]


def _findings(pages, end=242):
    return segment_chapter(
        pages, 47, "Nairobi City County Assembly", 239, end, 0,
        stop_at_appendix=False,
    )[0]


def test_nairobi_official_transport_ends_before_separate_historical_list():
    findings = _findings(_source_pages())
    assert [(f.vote, f.entity_name, f.paragraph_no, f.pdf_page) for f in findings] == [
        (47, "Nairobi City County Assembly", 645, 239)
    ]
    assert findings[0].finding_text.endswith(
        "In the circumstances, the internal controls in management of motor vehicles "
        "could not be confirmed."
    )
    assert "List of Unresolved Prior Years Matters" not in findings[0].finding_text
    assert "Audit Issues for 2019/2020" not in findings[0].finding_text
    assert "Noncompliance with Fiscal Responsibility Principles" not in findings[0].finding_text


def test_separate_table_spans_pages_and_next_structural_heading_resumes_findings():
    pages = _source_pages()
    pages.append(PageText(
        243,
        "No. Audit Issues for 2023/2024\n"
        "36. Prior matter with a wrapped\ncontinuation line\n"
        "REPORT ON LAWFULNESS AND EFFECTIVENESS IN THE USE OF PUBLIC RESOURCES\n"
        "Basis for Conclusion\n"
        "646. A New Current-Year Finding\nThe current-year issue is separate.\n230",
        "pdfplumber",
    ))
    findings = _findings(pages, 243)
    assert [f.paragraph_no for f in findings] == [645, 646]
    assert findings[1].finding_text == "A New Current-Year Finding The current-year issue is separate."
    assert findings[1].pdf_page == 243
    assert findings[1].heading == "Basis for Conclusion"


def test_malformed_detached_list_does_not_consume_later_structural_section():
    page = PageText(
        1,
        "Basis for Conclusion\n645. Official Transport\nFinding conclusion.\n"
        "List of Unresolved Prior Years Matters\n"
        "table header damaged\n1. Historical entry\nwrapped continuation\n"
        "Other Matter\n646. Current Finding\nCurrent detail.\n1",
        "pdfplumber",
    )
    findings, _ = segment_chapter([page], 47, "Assembly", 1, 1, 0)
    assert [(f.paragraph_no, f.finding_text) for f in findings] == [
        (645, "Official Transport Finding conclusion."),
        (646, "Current Finding Current detail."),
    ]


def test_detached_list_without_following_heading_resumes_unambiguous_paragraph():
    page = PageText(
        1,
        "645. Official Transport\nFinding conclusion.\n"
        "List of Unresolved Prior Years Matters\n"
        "No. Audit Issues for 2023/2024\n1. Pending Bills\n"
        "No. Audit Issues for 2023/2024\n2. Unsupported prior-year item\n"
        "646. Current Finding\nCurrent detail.\n1",
        "pdfplumber",
    )
    findings, _ = segment_chapter([page], 47, "Assembly", 1, 1, 0)
    assert [(f.paragraph_no, f.finding_text) for f in findings] == [
        (645, "Official Transport Finding conclusion."),
        (646, "Current Finding Current detail."),
    ]


def test_ambiguous_low_number_after_detached_list_is_not_fabricated():
    page = PageText(
        1,
        "2. Current Finding\nFinding conclusion.\n"
        "List of Unresolved Prior Years Matters\n"
        "No. Audit Issues for 2023/2024\n1. Old issue\n"
        "2. Another old issue\n3. Could be an old issue\n1",
        "pdfplumber",
    )
    findings, _ = segment_chapter([page], 47, "Assembly", 1, 1, 0)
    assert [(f.paragraph_no, f.finding_text) for f in findings] == [
        (2, "Current Finding Finding conclusion.")
    ]


def test_wrapped_standalone_list_heading_is_outside_current_finding():
    page = PageText(
        1,
        "645. Official Transport\nFinding conclusion.\n"
        "List of Unresolved Prior Years\nMatters\n"
        "No. Audit Issues for 2023/2024\n1. Old issue\n1",
        "pdfplumber",
    )
    findings, _ = segment_chapter([page], 47, "Assembly", 1, 1, 0)
    assert [(f.paragraph_no, f.finding_text) for f in findings] == [
        (645, "Official Transport Finding conclusion.")
    ]


def test_punctuated_or_hyphenated_standalone_list_heading_is_outside_finding():
    for title in (
        "List of Unresolved Prior Years Matters:",
        "List of Unresolved Prior-Year Matters",
    ):
        page = PageText(
            1,
            "645. Official Transport\nFinding conclusion.\n"
            f"{title}\nNo. Audit Issues for 2023/2024\n1. Old issue\n1",
            "pdfplumber",
        )
        findings, _ = segment_chapter([page], 47, "Assembly", 1, 1, 0)
        assert [(f.paragraph_no, f.finding_text) for f in findings] == [
            (645, "Official Transport Finding conclusion.")
        ]


def test_low_chapter_number_does_not_turn_later_table_row_into_finding():
    page = PageText(
        1,
        "4. Current Finding\nFinding conclusion.\n"
        "List of Unresolved Prior Years Matters\n"
        "No. Audit Issues for 2023/2024\n1. Old issue\n"
        "5. Another old issue in the same table\n1",
        "pdfplumber",
    )
    findings, _ = segment_chapter([page], 47, "Assembly", 1, 1, 0)
    assert [(f.paragraph_no, f.finding_text) for f in findings] == [
        (4, "Current Finding Finding conclusion.")
    ]


def test_hyphenated_prior_year_finding_retains_its_own_list():
    page = PageText(
        1,
        "4. Unresolved Prior-Year Audit Matters\n"
        "Several matters remained unresolved.\n"
        "List of Unresolved Prior Years Matters\n"
        "No. Audit Issues for 2023/2024\n1. Old issue\n1",
        "pdfplumber",
    )
    findings, _ = segment_chapter([page], 47, "Assembly", 1, 1, 0)
    assert len(findings) == 1
    assert "List of Unresolved Prior Years Matters" in findings[0].finding_text
    assert "1. Old issue" in findings[0].finding_text


def test_all_caps_historical_row_does_not_become_next_subsection():
    page = PageText(
        1,
        "CURRENT YEAR OVERSIGHT\n645. Official Transport\nFinding conclusion.\n"
        "List of Unresolved Prior Years Matters\n"
        "No. Audit Issues for 2023/2024\n1. Old issue\n"
        "REPORT ON FINANCIAL STATEMENTS\n"
        "Other Matter\n646. Current Finding\nBody.\n1",
        "pdfplumber",
    )
    findings, _ = segment_chapter([page], 47, "Assembly", 1, 1, 0)
    assert [f.paragraph_no for f in findings] == [645, 646]
    assert findings[1].sub_section is None
    assert findings[1].heading == "Other Matter"


def test_all_caps_historical_row_does_not_resume_low_numbered_findings():
    page = PageText(
        1,
        "4. Official Transport\nFinding conclusion.\n"
        "List of Unresolved Prior Years Matters\n"
        "No. Audit Issues for 2023/2024\n1. Old issue\n"
        "REPORT ON FINANCIAL STATEMENTS\n5. Old issue continued\n1",
        "pdfplumber",
    )
    findings, _ = segment_chapter([page], 47, "Assembly", 1, 1, 0)
    assert [(f.paragraph_no, f.finding_text) for f in findings] == [
        (4, "Official Transport Finding conclusion."),
    ]


def test_prior_year_finding_keeps_its_own_table_as_evidence():
    page = PageText(
        1,
        "Other Matter\n2. Unresolved Prior Year Audit Matters\n"
        "The prior audit matters remained unresolved.\n"
        "List of Unresolved Prior Years Matters\n"
        "No. Audit Issues for 2023/2024\n1. Pending Bills\n"
        "2. Unsupported cash and\ncash equivalents\n"
        "Basis for Conclusion\n3. Current Finding\nCurrent detail.\n1",
        "pdfplumber",
    )
    findings, _ = segment_chapter([page], 47, "Assembly", 1, 1, 0)
    assert [f.paragraph_no for f in findings] == [2, 3]
    assert "List of Unresolved Prior Years Matters" in findings[0].finding_text
    assert "2. Unsupported cash and cash equivalents" in findings[0].finding_text
