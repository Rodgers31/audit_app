"""A publisher outage must not be recorded as a parser failure.

On the 2026-09-04 nightly every COB URL failed:

    COB county page unavailable at https://cob.go.ke/...:
    [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
    certificate has expired (_ssl.c:1010)

The parser never ran. The run still recorded `parser_returned_nothing`, and
the staleness gate reported that for 18 consecutive runs — which sends the
next reader into the extraction code. The parser is fine: given the document
it produces 75 records.

The two states are different problems with different owners. "The publisher is
down" is theirs and usually transient; "we got the document and extracted
nothing" is ours. One reason for both cost a day.
"""

from unittest.mock import patch

import pytest
from seeding.domains.counties_budget import fetcher as F
from seeding.domains.counties_budget.fetcher import CobSourceUnreachable
from seeding.staleness import DECLARED_NO_SOURCE_REASONS


class _Settings:
    live_pdf_fetch_enabled = True
    counties_budget_prefer_live_source = True
    budgets_dataset_url = "file://seeding/real_data/budgets.json"


class _Client:
    def __init__(self, exc):
        self._exc = exc

    def get(self, *a, **k):
        raise self._exc


def _reasons_for(exc):
    """Run the fetch with every HTTP call raising ``exc``; capture the mark."""
    marks = []
    with patch.object(F, "mark_fixture", lambda d, **k: marks.append(k)), patch.object(
        F, "load_json_resource", lambda **k: []
    ):
        F.fetch_budget_payload(_Client(exc), _Settings())
    return marks[0] if marks else {}


class TestTransportIsNotParsing:
    def test_an_expired_certificate_is_reported_as_unreachable(self):
        """The literal 2026-09-04 failure."""
        mark = _reasons_for(
            Exception(
                "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                "certificate has expired (_ssl.c:1010)"
            )
        )
        assert mark.get("reason") == "source_unreachable"
        assert mark.get("reason") != "parser_returned_nothing"

    def test_the_detail_carries_the_transport_error(self):
        """Enough to see it was the publisher, without opening the run log."""
        mark = _reasons_for(Exception("[SSL: CERTIFICATE_VERIFY_FAILED] expired"))
        assert "CERTIFICATE_VERIFY_FAILED" in (mark.get("detail") or "")

    @pytest.mark.parametrize(
        "exc",
        [
            ConnectionError("connection refused"),
            TimeoutError("read timed out"),
            Exception("HTTP 503 Service Unavailable"),
        ],
    )
    def test_every_transport_failure_reports_unreachable(self, exc):
        assert _reasons_for(exc).get("reason") == "source_unreachable"


class TestItStillFailsTheGate:
    def test_an_outage_is_not_excused_as_a_by_design_gap(self):
        """source_unreachable must stay a FAIL.

        A publisher being down is a real problem to surface — it is only
        misfiled, not acceptable. Only `no_live_source` downgrades to WARN.
        """
        assert "source_unreachable" not in DECLARED_NO_SOURCE_REASONS


class TestTheParserIsNotAccused:
    def test_unreachable_raises_rather_than_returning_empty(self):
        """Returning None is what made an outage indistinguishable from a
        parse that found nothing."""
        with pytest.raises(CobSourceUnreachable):
            F._fetch_from_cob_county_pdf(
                _Client(Exception("[SSL: CERTIFICATE_VERIFY_FAILED] expired")),
                _Settings(),
            )

    def test_parser_returned_nothing_is_reserved_for_a_real_empty_parse(self):
        """The reason survives — for the case it actually describes: the page
        loaded, a PDF was found, and extraction produced no records."""
        marks = []
        with patch.object(F, "mark_fixture", lambda d, **k: marks.append(k)), patch.object(
            F, "load_json_resource", lambda **k: []
        ), patch.object(F, "_fetch_from_cob_county_pdf", lambda *a, **k: []):
            F.fetch_budget_payload(_Client(Exception("unused")), _Settings())
        assert marks[0].get("reason") == "parser_returned_nothing"
