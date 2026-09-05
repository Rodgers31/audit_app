"""Decide candidacy before downloading, not after.

The audits domain fetches every candidate and only then hands it to a parser,
so a document the parser refuses is downloaded first and refused second. On
2026-09-05 that aborted the whole domain:

    VOLUME II    6.6 MB, 232 pages, extract  26s
    VOLUME I     7.6 MB, 469 pages, extract  40s
    COVID funds  262.5 MB
    DomainTimeoutError: domain exceeded 600s budget

The two volumes carrying all 47 counties cost 66s between them. The budget
went on a 262MB thematic audit the parser then refused for naming no auditee,
and the run wrote nothing.

The filter is deliberately CONSERVATIVE: it rejects only what it can
positively identify as not a county financial audit, and keeps anything it
cannot classify. Silently dropping a real report would lose audit findings —
far worse than spending one download on something the parser then refuses.
"""

import pytest

from seeding.domains.audits.candidates import (
    classify_county_audit_candidate,
    split_county_audit_candidates,
)

BASE = "https://www.oagkenya.go.ke/wp-content/uploads/2023/11/"

# The five real candidates the domain listed on 2026-09-05.
REAL = [
    "UTILIZATION-OF-COVID-19-FUNDS-BY-COUNTY-GOVERMENTS-2020.pdf",
    "County-Assembly-of-Homa-Bay-2021-2022.pdf",
    "EMERGENCY-MEDICAL-CARE-SERVICES-IN-KAJIADO-COUNTY_compressed.pdf",
    "REPORT-OF-THE-AUDITOR-GENERAL-FOR-THE-COUNTY-GOVERNMENTS-FOR-THE-YEAR-2020-2021-_VOLUME-I-COUNTY-EXECUTIVES.pdf",
    "REPORT-OF-THE-AUDITOR-GENERAL-FOR-THE-COUNTY-GOVERNMENTS-FOR-THE-YEAR-2020-2021-_VOLUME-II-COUNTY-ASSEMBLIES.pdf",
]


class TestTheRealCandidateSet:
    def test_the_262mb_thematic_audit_is_dropped_before_download(self):
        keep, rejected = split_county_audit_candidates([BASE + n for n in REAL])
        dropped = {w for _, w in rejected}
        assert "thematic_covid_audit" in dropped
        assert not any("COVID" in u for u in keep)

    def test_the_performance_audit_is_dropped(self):
        keep, rejected = split_county_audit_candidates([BASE + n for n in REAL])
        assert "performance_audit" in {w for _, w in rejected}
        assert not any("EMERGENCY" in u for u in keep)

    def test_all_three_real_county_audits_are_kept(self):
        """The ones carrying 1,509 findings across 47 counties."""
        keep, _ = split_county_audit_candidates([BASE + n for n in REAL])
        assert len(keep) == 3
        assert any("Homa-Bay" in u for u in keep)
        assert sum("COUNTY-GOVERNMENTS" in u for u in keep) == 2


class TestClassification:
    @pytest.mark.parametrize(
        "name,reason",
        [
            ("County-Assembly-of-Homa-Bay-2021-2022.pdf", "single_entity_report"),
            ("County-Executive-of-Kwale-2022-2023.pdf", "single_entity_report"),
            ("County-Government-of-Nakuru-2023-2024.pdf", "single_entity_report"),
        ],
    )
    def test_single_entity_shapes_are_kept(self, name, reason):
        keep, why = classify_county_audit_candidate(BASE + name)
        assert keep and why == reason

    def test_a_consolidated_volume_is_kept(self):
        keep, why = classify_county_audit_candidate(BASE + REAL[3])
        assert keep and why == "consolidated_volume"

    @pytest.mark.parametrize(
        "name,reason",
        [
            ("Auditor-Generals-Popular-Report-on-National-Government.pdf", "popular_report"),
            ("SPECIAL-AUDIT-OF-SOMETHING.pdf", "special_audit"),
            ("Terms-of-Reference.pdf", "not_an_audit_report"),
        ],
    )
    def test_other_document_classes_are_dropped(self, name, reason):
        keep, why = classify_county_audit_candidate(BASE + name)
        assert not keep and why == reason


class TestItFailsOpen:
    def test_an_unrecognised_name_is_kept_not_dropped(self):
        """The parser's gates are the real decision.

        A filter that dropped what it did not recognise would lose findings
        silently — the failure mode this repo keeps finding.
        """
        keep, why = classify_county_audit_candidate(BASE + "Nyeri-2024.pdf")
        assert keep and why == "unclassified_kept"

    def test_a_county_audit_wins_over_a_reject_word(self):
        """Order matters: a real report mentioning 'special audit' is kept."""
        keep, why = classify_county_audit_candidate(
            BASE + "County-Assembly-of-Kisumu-special-audit-2022.pdf"
        )
        assert keep and why == "single_entity_report"

    def test_an_empty_url_is_kept_rather_than_silently_discarded(self):
        keep, _ = classify_county_audit_candidate("")
        assert keep
