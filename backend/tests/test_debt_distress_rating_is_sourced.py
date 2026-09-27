"""Kenya's risk-of-debt-distress rating is the IMF's, quoted and cited.

Issue #269. ``/debt/national`` used to build the rating from a ratio test::

    "risk_level": "High" if debt_to_gdp_ratio > 65 else "Moderate" …
    "assessment": "Kenya's debt remains elevated. The IMF classifies Kenya at
                   high risk of debt distress." if debt_to_gdp_ratio > 65 …

The homepage then showed this as "High risk of debt distress · IMF". The 65%
threshold has no source, and no IMF document was read to produce the
sentence. Production was at 69.3%, so the output happened to agree with the
IMF. It agreed by coincidence. At 65.0% the site would say "Moderate" while
the IMF says High.

The rating now comes from the joint Bank-Fund DSA verbatim, with title, URL,
date and page. These tests pin four things:

1. The published rating does not move with the debt ratio.
2. Every IMF attribution carries a citation.
3. The declaration matches the IMF's own page, via the committed extracts.
4. The rating survives a database outage, because it never came from the
   database.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from models import DebtCategory, Entity, EntityType, ImfWeoObservation, Loan

FIXTURES = Path(__file__).parent / "fixtures" / "imf"
DSA_PAGE = FIXTURES / "cr24316_dsa_page132.txt"
DSA_LIST = FIXTURES / "dsalist_2026-03-31_kenya.txt"

VINTAGE = datetime(2026, 9, 7, tzinfo=timezone.utc)


def _body(path: Path) -> str:
    """The extract without its provenance header."""
    return path.read_text(encoding="utf-8").split("# ---\n", 1)[1]


def national_debt(client) -> dict:
    from main import clear_all_caches

    clear_all_caches()
    body = client.get("/api/v1/debt/national").json()
    assert body["status"] == "success", body
    return body["data"]


@pytest.fixture()
def register(db_session, seed_country, seed_source_doc):
    """A one-row national register, so that ``/debt/national`` succeeds."""
    entity = Entity(
        id=900,
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="Republic of Kenya",
        slug="republic-of-kenya",
    )
    db_session.add(entity)
    db_session.add(
        Loan(
            entity_id=900,
            lender="Domestic Treasury Bonds",
            debt_category=DebtCategory.DOMESTIC_BONDS,
            principal=5879.0e9,
            outstanding=5879.0e9,
            issue_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            currency="KES",
            source_document_id=seed_source_doc.id,
        )
    )
    db_session.commit()
    return db_session


def _set_ratio(db_session, value: float) -> None:
    """Make ``value`` the IMF WEO debt-to-GDP headline ``/debt/national`` reads."""
    db_session.query(ImfWeoObservation).delete()
    db_session.add(
        ImfWeoObservation(
            country_code="KEN", indicator="GGXWDG_NGDP", year=2025, value=value,
            is_projection=False, vintage=VINTAGE, source="imf_datamapper",
        )
    )
    db_session.commit()


def _uncited_imf_strings(node, path="debt_sustainability", cited=False):
    """Yield ``(path, text)`` for every string that names the IMF with no
    citation on it or on any dict enclosing it."""
    if isinstance(node, dict):
        cited = cited or _cited(node)
        for k, v in node.items():
            if isinstance(v, str):
                if re.search(r"\bIMF\b", v) and not cited:
                    yield f"{path}.{k}", v
            else:
                yield from _uncited_imf_strings(v, f"{path}.{k}", cited)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _uncited_imf_strings(v, f"{path}[{i}]", cited)


def _cited(d: dict) -> bool:
    src = d.get("source") if isinstance(d.get("source"), dict) else None
    return bool(src and src.get("url") and src.get("page") and src.get("dsa_date"))


# ── 1. The rating is not a function of the debt ratio ──────────────────────

@pytest.mark.parametrize("ratio", [64.0, 65.0, 69.3])
def test_the_rating_does_not_move_with_debt_to_gdp(client, register, ratio):
    """Before the fix, 64.0 and 65.0 gave "Moderate" and 69.3 gave "High",
    all against one IMF rating of High. The ratio is still published. The
    rating is not derived from it."""
    _set_ratio(register, ratio)
    data = national_debt(client)
    ds = data["debt_sustainability"]

    assert data["debt_to_gdp_ratio"] == pytest.approx(ratio)
    # No second, synthesized rating beside the published one.
    assert "risk_level" not in ds, (
        f"a rating of {ds['risk_level']!r} was derived from debt-to-GDP {ratio}"
    )
    assert "assessment" not in ds
    assert ds["imf_dsa"]["overall_risk_of_debt_distress"] == "High"
    assert ds["imf_dsa"]["risk_of_external_debt_distress"] == "High"


def test_every_imf_attribution_carries_its_citation(client, register):
    """No string may name the IMF unless it sits beside a URL, a date and a
    page. Before the fix, ``assessment`` named the IMF with no source at all."""
    _set_ratio(register, 69.3)
    ds = national_debt(client)["debt_sustainability"]

    uncited = list(_uncited_imf_strings(ds))
    assert not uncited, f"IMF named without a citation: {uncited}"

    src = ds["imf_dsa"]["source"]
    assert src["series"] == "IMF Country Report No. 24/316"
    assert src["url"].startswith("https://www.imf.org/")
    assert src["page"] == 132
    assert src["dsa_date"] == "2024-10-18"


# ── 2. The declaration is what the IMF printed ─────────────────────────────

def test_the_declared_rating_is_verbatim_from_the_dsa_page():
    """Each declared row must appear, label and value together, on PDF
    p.132 of CR 24/316. This catches a transcription error, and a
    declaration updated without its receipt."""
    from services.imf_dsa import kenya_dsa_rating

    r = kenya_dsa_rating()
    page = _body(DSA_PAGE)
    rows = {
        "Risk of external debt distress": r["risk_of_external_debt_distress"],
        "Overall risk of debt distress": r["overall_risk_of_debt_distress"],
        "Granularity in the risk rating": r["granularity_in_the_risk_rating"],
        "Application of judgment": r["application_of_judgment"],
    }
    for label, value in rows.items():
        assert re.search(rf"^\s*{re.escape(label)}\s+{re.escape(value)}\s*$", page, re.M), (
            f"{label!r} = {value!r} is not what p.132 prints"
        )
    assert "Joint Bank-Fund Debt Sustainability Analysis" in page
    assert "DEBT SUSTAINABILITY ANALYSIS" in page
    # The date on the DSA's cover is the declared dsa_date.
    assert re.search(r"^October 18, 2024$", page, re.M)
    assert r["source"]["dsa_date"] == "2024-10-18"


def test_the_imf_register_confirms_it_was_the_latest_dsa():
    """The IMF's DSA register, as of 31 Mar 2026, lists this DSA as Kenya's
    latest, with the same external rating."""
    from services.imf_dsa import kenya_dsa_rating

    r = kenya_dsa_rating()
    reg = _body(DSA_LIST)
    assert "As of March 31, 2026" in reg
    assert r["latest_confirmed"]["as_of"] == "2026-03-31"

    row = re.search(r"^(\d+)\s+Kenya\b.*?\s(\d+)/(\d+)/(\d{4})\s+(\S+)\s+(\S+)\s+Yes\s*$", reg, re.M)
    assert row, "Kenya row missing from the register extract"
    count, m, d, y, external, assessment = row.groups()
    assert int(count) == r["latest_confirmed"]["row"]
    assert f"{y}-{int(m):02d}-{int(d):02d}" == r["source"]["published"]
    assert external == r["risk_of_external_debt_distress"]
    assert assessment == r["granularity_in_the_risk_rating"]


def test_the_declaration_cannot_be_mutated_through_a_caller():
    from services.imf_dsa import kenya_dsa_rating

    kenya_dsa_rating()["overall_risk_of_debt_distress"] = "Low"
    kenya_dsa_rating()["source"]["page"] = 1
    assert kenya_dsa_rating()["overall_risk_of_debt_distress"] == "High"
    assert kenya_dsa_rating()["source"]["page"] == 132


# ── 3. It does not depend on our database ──────────────────────────────────

def test_the_rating_survives_an_empty_register(client, db_session):
    """With no loan register, every figure is null with a reason. The IMF
    rating is not our figure, so it is still published. Before the fix this
    branch returned ``debt_sustainability: {}``."""
    from main import clear_all_caches

    clear_all_caches()
    body = client.get("/api/v1/debt/national").json()
    assert body["status"] == "no_data"
    assert body["data"]["total_outstanding"] is None
    ds = body["data"]["debt_sustainability"]
    assert ds["imf_dsa"]["overall_risk_of_debt_distress"] == "High"
    assert ds["imf_dsa"]["source"]["page"] == 132
