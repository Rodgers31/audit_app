"""The county page shows an official's name only when a publisher supplied it (#231).

The officials card used to take the deputy governor, CEC Finance, speaker,
party and term from a hand-typed frontend file, and the governor partly from
``enhanced_county_data.json`` by way of bootstrap. For Meru that put the
sitting governor's name beside his impeached predecessor's party and term,
and listed him again as deputy.

The comprehensive endpoint now publishes a governor and a deputy only when
the Council of Governors supplied them (``*_provenance`` in entity.meta), and
says where each one came from.
"""

import pytest

COG = {
    "source": "Council of Governors",
    "source_url": "https://cog.go.ke/current-governors/",
    "source_document_id": 1,
    "extractor": "cog_governors",
    "fetched_at": "2026-09-26T03:00:00+00:00",
}
COG_DEPUTIES = {**COG, "source_url": "https://cog.go.ke/current-deputy-governors/"}


def _meru(db_session, seed_country, meta):
    from models import Entity, EntityType

    db_session.add(
        Entity(
            id=12,
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name="Meru County",
            slug="meru-county",
            meta=meta,
        )
    )
    db_session.commit()


def _get(client):
    res = client.get("/api/v1/counties/012/comprehensive")
    assert res.status_code == 200, res.text
    return res.json()


def test_sourced_officials_are_published_with_their_source(
    client, db_session, seed_country
):
    _meru(
        db_session,
        seed_country,
        {
            "governor": "Isaac Mutuma M’ethingia",
            "governor_provenance": COG,
            "deputy_governor": "Linda Kiome",
            "deputy_governor_provenance": COG_DEPUTIES,
        },
    )
    body = _get(client)
    assert body["governor"] == "Isaac Mutuma M’ethingia"
    assert body["deputy_governor"] == "Linda Kiome"
    assert body["officials_source"]["governor"]["source_url"] == COG["source_url"]
    assert body["officials_source"]["deputy_governor"]["source_url"] == COG_DEPUTIES["source_url"]
    assert body["officials_source"]["deputy_governor"]["fetched_at"] == COG["fetched_at"]


def test_a_name_with_no_publisher_is_not_published(client, db_session, seed_country):
    """What bootstrap writes from enhanced_county_data.json: a name, no source."""
    _meru(db_session, seed_country, {"governor": "Kawira Mwangaza"})
    body = _get(client)
    assert body["governor"] is None
    assert body["deputy_governor"] is None
    assert body["officials_source"] == {"governor": None, "deputy_governor": None}
