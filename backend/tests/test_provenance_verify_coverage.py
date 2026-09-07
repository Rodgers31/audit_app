"""Four published tables could not be traced to a source at all.

``GET /api/v1/provenance/verify/{table}`` had branches for population_data,
gdp_data, audits, loans, budget_lines and debt_timeline, and answered
``400 Unknown table`` for ``fiscal_summaries``, ``revenue_by_source``,
``pending_bills`` and ``counties`` — four tables whose figures the site
publishes. On the one endpoint whose entire job is answering "where did this
number come from?", a 400 is not an answer.

Three of the four have a chain: ``FiscalSummary``, ``RevenueBySource`` and the
pending-bill ``Loan`` rows all carry a ``source_document_id``. The fourth does
not — ``entities`` has no source-document column at all — so that branch says
so in words rather than leaving the table unmentioned.
"""

from datetime import datetime

import pytest
from models import (
    DebtCategory,
    DocumentStatus,
    DocumentType,
    FiscalSummary,
    Loan,
    RevenueBySource,
    SourceDocument,
)


@pytest.fixture()
def hashed_doc(db_session, seed_country):
    """A source document that carries an md5, unlike the ETL-written ones."""
    doc = SourceDocument(
        id=900,
        country_id=seed_country.id,
        publisher="Office of the Controller of Budget (OCOB)",
        title="Treasury BROP FY 2024/25",
        url="https://treasury.go.ke/brop-2024-25.pdf",
        md5="7e6a6850102a3cadcba38e1f7af9cae3",
        fetch_date=datetime(2026, 4, 26),
        doc_type=DocumentType.REPORT,
        status=DocumentStatus.AVAILABLE,
    )
    db_session.add(doc)
    db_session.commit()
    return doc


class TestProvenanceVerifyCoverage:
    """``verify`` answered "Unknown table" for four tables whose figures the
    site publishes. A 400 is not a provenance answer."""

    @pytest.mark.parametrize(
        "table", ["fiscal_summaries", "revenue_by_source", "pending_bills", "counties"]
    )
    def test_table_is_not_unknown(self, client, table):
        resp = client.get(f"/api/v1/provenance/verify/{table}")
        assert resp.status_code == 200, (
            f"{table} is published by this API but cannot be traced: "
            f"{resp.json()}"
        )
        assert resp.json()["table"] == table

    def test_fiscal_summaries_resolves_to_its_document(
        self, client, db_session, hashed_doc
    ):
        db_session.add(
            FiscalSummary(
                fiscal_year="FY 2024/25",
                appropriated_budget=4_490_000_000_000,
                source_document_id=hashed_doc.id,
            )
        )
        db_session.commit()
        body = client.get(
            "/api/v1/provenance/verify/fiscal_summaries?year=2024"
        ).json()
        assert body["source_url"] == hashed_doc.url
        assert body["verification_status"] == "publishable"
        assert "4,490,000,000,000" in body["value"]

    def test_fiscal_summaries_absent_figure_is_not_zero(
        self, client, db_session, hashed_doc
    ):
        db_session.add(
            FiscalSummary(
                fiscal_year="FY 2019/20",
                appropriated_budget=None,
                source_document_id=hashed_doc.id,
            )
        )
        db_session.commit()
        body = client.get(
            "/api/v1/provenance/verify/fiscal_summaries?year=2019"
        ).json()
        assert body["value"] is None
        assert "no appropriated budget" in body["reason"]

    def test_revenue_by_source_names_the_row_it_verified(
        self, client, db_session, hashed_doc
    ):
        db_session.add_all(
            [
                RevenueBySource(
                    fiscal_year="FY 2024/25",
                    revenue_type="PAYE",
                    category="tax",
                    amount_billion_kes=561.0,
                    source_document_id=hashed_doc.id,
                ),
                RevenueBySource(
                    fiscal_year="FY 2024/25",
                    revenue_type="VAT",
                    category="tax",
                    amount_billion_kes=327.3,
                    source_document_id=hashed_doc.id,
                ),
            ]
        )
        db_session.commit()
        body = client.get(
            "/api/v1/provenance/verify/revenue_by_source?year=2024"
        ).json()
        assert "PAYE" in body["value"]
        assert "FY 2024/25" in body["value"]
        assert body["source_url"] == hashed_doc.url

    def test_pending_bills_resolves_to_its_document(
        self, client, db_session, seed_entity, hashed_doc
    ):
        db_session.add(
            Loan(
                entity_id=seed_entity.id,
                lender="Pending Bills — County Governments (Nairobi County)",
                debt_category=DebtCategory.PENDING_BILLS,
                principal=86_770_000_000,
                outstanding=86_770_000_000,
                currency="KES",
                issue_date=datetime(2025, 6, 30),
                source_document_id=hashed_doc.id,
                provenance=[{"source": "cob_pending_bills_etl"}],
            )
        )
        db_session.commit()
        body = client.get("/api/v1/provenance/verify/pending_bills").json()
        assert body["source_url"] == hashed_doc.url
        assert body["verification_status"] == "publishable"
        assert body["provenance_chain"]

    def test_pending_bills_modelled_fixture_is_not_graded_sourced(
        self, client, db_session, seed_entity, hashed_doc
    ):
        db_session.add(
            Loan(
                entity_id=seed_entity.id,
                lender="County Pending Bills",
                debt_category=DebtCategory.PENDING_BILLS,
                principal=1_000_000_000,
                outstanding=1_000_000_000,
                currency="KES",
                issue_date=datetime(2025, 6, 30),
                source_document_id=hashed_doc.id,
                provenance=[
                    {"source": "bootstrap", "dataset": "enhanced_county_data.json"}
                ],
            )
        )
        db_session.commit()
        body = client.get("/api/v1/provenance/verify/pending_bills").json()
        assert body["verification_status"] == "modelled"
        assert "modelled" in body["reason"]

    def test_counties_says_the_chain_does_not_exist(
        self, client, db_session, seed_entity
    ):
        """`entities` carries no source_document_id. Saying so is the answer;
        omitting the table said it only to a reader who guessed the name."""
        body = client.get("/api/v1/provenance/verify/counties").json()
        assert body["verification_status"] == "unverified"
        assert "no source document" in body["reason"]
        assert body["source_url"] is None

    def test_counties_still_reports_a_missing_entity(self, client, seed_entity):
        """"No such county" and "counties have no provenance chain" are
        different answers; the response must not lose the first."""
        body = client.get(
            "/api/v1/provenance/verify/counties?entity_id=99999"
        ).json()
        assert body["value"] is None
        assert "no_county_for_entity_id" in body["reason"]
        assert "no source document" in body["reason"]

    def test_a_genuinely_unknown_table_still_400s(self, client):
        """The four names are answered; an invented one must not be."""
        assert client.get("/api/v1/provenance/verify/not_a_table").status_code == 400


class TestVerifyStatesItsOwnLimit:
    """The endpoint stops at "resolves to a document". That sentence must not
    be softened — only extended with facts it leaves open."""

    def test_reason_still_says_the_document_was_not_fetched(
        self, client, db_session, hashed_doc
    ):
        db_session.add(
            FiscalSummary(
                fiscal_year="FY 2024/25",
                appropriated_budget=4_490_000_000_000,
                source_document_id=hashed_doc.id,
            )
        )
        db_session.commit()
        body = client.get("/api/v1/provenance/verify/fiscal_summaries").json()
        assert body["verification_status"] != "verified"
        assert "has not been fetched or validated by this endpoint" in body["reason"]

    def test_reason_reports_whether_an_md5_is_on_file(
        self, client, db_session, seed_country, hashed_doc
    ):
        """Two documents, one with an md5 and one without, must not describe
        their own integrity the same way."""
        unhashed = SourceDocument(
            id=902,
            country_id=seed_country.id,
            publisher="Kenya Revenue Authority",
            title="KRA Annual Revenue Performance Report",
            url="https://kra.go.ke/revenue-2024-25",
            fetch_date=datetime(2026, 3, 25),
            md5=None,
            doc_type=DocumentType.REPORT,
            status=DocumentStatus.AVAILABLE,
        )
        db_session.add(unhashed)
        db_session.add_all(
            [
                FiscalSummary(
                    fiscal_year="FY 2024/25",
                    appropriated_budget=4_490_000_000_000,
                    source_document_id=hashed_doc.id,
                ),
                RevenueBySource(
                    fiscal_year="FY 2024/25",
                    revenue_type="PAYE",
                    category="tax",
                    amount_billion_kes=561.0,
                    source_document_id=unhashed.id,
                ),
            ]
        )
        db_session.commit()
        with_md5 = client.get(
            "/api/v1/provenance/verify/fiscal_summaries"
        ).json()["reason"]
        without_md5 = client.get(
            "/api/v1/provenance/verify/revenue_by_source"
        ).json()["reason"]
        assert "an md5 is on file" in with_md5
        assert "no md5 is on file" in without_md5
