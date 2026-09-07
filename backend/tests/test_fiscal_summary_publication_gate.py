"""A published fiscal figure must name a page a reader can turn to.

Issue #137 step (b): ``fiscal_summaries`` joins the provenance ladder at
Tier B — a **locator**, not an ``extraction_id``. A reader cannot open an
extraction id; ``page_ref`` is a citation they can check. The FY2026/27
headline is the case in point: it carries
``"voted total PDF p.11; CFS summary PDF p.1193"`` and no ``extraction_id``
at all.

MEASURED ON PRODUCTION, 2026-09-07 (alembic ``ce6ed007f696``)
-------------------------------------------------------------
``fiscal_summaries`` holds 29 rows. Five carry a locator:

    FY 2026/27  5,485.7B  "voted total PDF p.11; CFS summary PDF p.1193"
    FY 2025/26  4,690.0B  "Executive Summary, report p.xxii (PDF p.23)"
    FY 2024/25  4,490.0B  "Executive Summary, report p.xxviii (PDF p.29)"
    FY 2023/24  4,340.0B  "s.3.2, report p.17 (PDF p.39)"
    FY 2022/23  3,675.0B  "s.3.2, report p.16 (PDF p.37)"

Twenty-four do not: **19 empty shells** back to FY1992/93 with
``appropriated_budget IS NULL``, and **5 rows carrying real budget figures** —
FY2017/18 through FY2021/22, KES 1,924.5B to 3,380.9B.

WHAT THIS COSTS: NOTHING TODAY, AND THAT IS THE POINT
-----------------------------------------------------
"24 rows disappear from the query" and "the page looks the same" are different
claims. Only the second one matters, and it was checked against the live API
before this gate was written:

    /api/v1/fiscal/summary              history: 5 rows, exactly the five above
    /api/v1/budget/overview             fiscal_history: the same 5
    /api/v1/dashboards/national/fiscal-outturns
                                        series: 4 (needs revenue AND expenditure)

So the 24 are **already** unpublished. But not for this reason, and not
stated. Each endpoint drops them with its own ad-hoc completeness rule —
"at least 3 of appropriated_budget / total_revenue / total_borrowing /
county_allocation", written out twice (``main.py:8138`` and ``:9058``) — which
is a question about *substance*, not about *provenance*.

The two rules coincide on today's data, exactly:

    fiscal_year   key_fields   has_locator
    FY 2026/27         3            yes
    FY 2025/26         4            yes
    FY 2024/25         4            yes
    FY 2023/24         4            yes
    FY 2022/23         4            yes
    FY 2021/22         1            no
    FY 2020/21         1            no
    FY 2019/20         1            no
    FY 2018/19         1            no
    FY 2017/18         1            no

They will not keep coinciding — they are not the same question — and today
neither of them tells a reader that five years of national budget history were
dropped, or why. Withholding is itself a claim. A response that silently loses
FY2017/18..FY2021/22 asserts, by omission, that Kenya's budget history begins
in 2022.

This suite fixes the reason to the locator and requires the omission to be
stated.
"""

import pytest


FY_WITH_LOCATOR = {
    "FY 2026/27": ("voted total PDF p.11; CFS summary PDF p.1193", 5_485_700_000_000),
    "FY 2025/26": ("Executive Summary, report p.xxii (PDF p.23)", 4_690_000_000_000),
    "FY 2024/25": ("Executive Summary, report p.xxviii (PDF p.29)", 4_490_000_000_000),
    "FY 2023/24": ("s.3.2, report p.17 (PDF p.39)", 4_340_000_000_000),
    "FY 2022/23": ("s.3.2, report p.16 (PDF p.37)", 3_675_000_000_000),
}

#: Real budget figures with no locator. These are the rows the gate costs.
FY_NO_LOCATOR_WITH_FIGURE = {
    "FY 2021/22": 3_380_900_000_000,
    "FY 2020/21": 2_837_400_000_000,
    "FY 2019/20": 2_142_400_000_000,
    "FY 2018/19": 1_924_500_000_000,
    "FY 2017/18": 2_207_600_000_000,
}

#: A sample of the 19 shells: no locator and no figure either.
FY_EMPTY_SHELLS = ["FY 1992/93", "FY 2000/01", "FY 2010/11"]


def _seed_production_shape(db_session):
    """The ten figure-bearing rows plus three shells, as production holds them."""
    from models import FiscalSummary

    for fy, (page_ref, budget) in FY_WITH_LOCATOR.items():
        db_session.add(
            FiscalSummary(
                fiscal_year=fy,
                appropriated_budget=budget,
                total_revenue=budget * 0.55,
                total_borrowing=budget * 0.25,
                county_allocation=budget * 0.09,
                unit="KES",
                page_ref=page_ref,
            )
        )
    for fy, budget in FY_NO_LOCATOR_WITH_FIGURE.items():
        db_session.add(
            FiscalSummary(
                fiscal_year=fy, appropriated_budget=budget, unit="KES", page_ref=None
            )
        )
    for fy in FY_EMPTY_SHELLS:
        db_session.add(FiscalSummary(fiscal_year=fy, unit="KES", page_ref=None))
    db_session.commit()


class TestTheCriterion:
    """What the gate admits, and what it refuses."""

    def _published(self, db_session):
        """The gate applied the way a read site applies it.

        The predicate is Python, not a SQL criterion, and deliberately so: the
        page-locator rule already exists once, in ``_has_page_locator``, and
        expressing "is this a positive page number?" again in SQL would need a
        second copy of it — with a regex that differs between Postgres and
        SQLite. Two copies of a rule that must agree is the exact drift this
        module was written to prevent. ``fiscal_summaries`` holds 29 rows and
        every read site already materialises them, so there is nothing to buy.
        """
        from models import FiscalSummary
        from services.publication_gate import publishable_fiscal_summaries

        rows = db_session.query(FiscalSummary).all()
        return {r.fiscal_year for r in publishable_fiscal_summaries(rows)}

    def test_a_row_with_a_locator_publishes(self, db_session):
        _seed_production_shape(db_session)
        assert "FY 2026/27" in self._published(db_session)

    def test_a_row_without_a_locator_is_withheld(self, db_session):
        """FY2021/22 carries KES 3,380.9B and no page reference."""
        _seed_production_shape(db_session)
        assert "FY 2021/22" not in self._published(db_session)

    def test_it_publishes_exactly_the_five_locator_rows(self, db_session):
        _seed_production_shape(db_session)
        assert self._published(db_session) == set(FY_WITH_LOCATOR)

    @pytest.mark.parametrize("locator", ["", "   ", "\t\n"])
    def test_blank_is_not_a_locator(self, db_session, locator):
        """Reported on PR #135 for the audits gate: `page_ref="   "` read as present."""
        from models import FiscalSummary

        db_session.add(
            FiscalSummary(
                fiscal_year="FY 2099/00", appropriated_budget=1, unit="KES",
                page_ref=locator,
            )
        )
        db_session.commit()
        assert "FY 2099/00" not in self._published(db_session)

    @pytest.mark.parametrize("locator", ["0", "0.0", "-3"])
    def test_page_zero_is_not_a_citation(self, db_session, locator):
        """Page 0 of a 400-page report is not somewhere a reader can turn."""
        from models import FiscalSummary

        db_session.add(
            FiscalSummary(
                fiscal_year="FY 2098/99", appropriated_budget=1, unit="KES",
                page_ref=locator,
            )
        )
        db_session.commit()
        assert "FY 2098/99" not in self._published(db_session)

    def test_a_textual_locator_is_accepted_on_its_own_terms(self, db_session):
        """"Annex VII" is a place in a document even though it is not a number."""
        from models import FiscalSummary

        db_session.add(
            FiscalSummary(
                fiscal_year="FY 2097/98", appropriated_budget=1, unit="KES",
                page_ref="Annex VII",
            )
        )
        db_session.commit()
        assert "FY 2097/98" in self._published(db_session)


class TestTheEndpointStillPublishesWhatItPublished:
    """The positive control. A gate that changes a figure has broken something."""

    def test_the_same_five_years_are_served(self, db_session, client):
        _seed_production_shape(db_session)
        body = client.get("/api/v1/fiscal/summary").json()
        served = {r["fiscal_year"] for r in body["history"]}
        assert served == set(FY_WITH_LOCATOR), (
            f"the published set changed: {sorted(served)}"
        )

    def test_the_figures_are_unchanged(self, db_session, client):
        _seed_production_shape(db_session)
        body = client.get("/api/v1/fiscal/summary").json()
        got = {r["fiscal_year"]: r["appropriated_budget"] for r in body["history"]}
        for fy, (_, budget) in FY_WITH_LOCATOR.items():
            assert got[fy] == pytest.approx(float(budget)), f"{fy} moved"

    def test_the_headline_year_is_still_fy2026_27(self, db_session, client):
        """The row this whole ladder was argued from must survive its own gate."""
        _seed_production_shape(db_session)
        body = client.get("/api/v1/fiscal/summary").json()
        assert body["current"]["fiscal_year"] == "FY 2026/27"
        assert body["current"]["appropriated_budget"] == pytest.approx(
            5_485_700_000_000.0
        )


class TestTheOmissionIsStated:
    """Withholding is a claim. A silently shorter list is an assertion about Kenya."""

    def test_the_response_says_how_many_were_withheld(self, db_session, client):
        _seed_production_shape(db_session)
        body = client.get("/api/v1/fiscal/summary").json()
        assert "withheld" in body, (
            "the response drops 8 of 13 seeded rows and says nothing about it"
        )
        assert body["withheld"]["count"] == 8

    def test_it_says_why_in_words_a_reader_can_act_on(self, db_session, client):
        _seed_production_shape(db_session)
        body = client.get("/api/v1/fiscal/summary").json()
        reasons = body["withheld"]["by_reason"]
        assert reasons.get("no_page_reference") == 8
        assert sum(reasons.values()) == body["withheld"]["count"], (
            "the breakdown must account for every withheld row"
        )

    def test_it_names_the_years_so_the_gap_is_checkable(self, db_session, client):
        """A count alone does not tell a reader WHICH years are missing."""
        _seed_production_shape(db_session)
        body = client.get("/api/v1/fiscal/summary").json()
        named = set(body["withheld"]["fiscal_years"])
        assert set(FY_NO_LOCATOR_WITH_FIGURE) <= named, (
            "the five years that carry real budget figures must be named; "
            f"got {sorted(named)}"
        )

    def test_a_fully_published_table_states_zero_rather_than_omitting_the_key(
        self, db_session, client
    ):
        """Absence of the key would read as "nothing withheld" by luck.

        A caller cannot tell "this build has no disclosure" from "there was
        nothing to disclose" unless the key is always present.
        """
        from models import FiscalSummary

        for fy, (page_ref, budget) in FY_WITH_LOCATOR.items():
            db_session.add(
                FiscalSummary(
                    fiscal_year=fy, appropriated_budget=budget,
                    total_revenue=budget * 0.55, total_borrowing=budget * 0.25,
                    county_allocation=budget * 0.09, unit="KES", page_ref=page_ref,
                )
            )
        db_session.commit()
        body = client.get("/api/v1/fiscal/summary").json()
        assert body["withheld"]["count"] == 0
        assert body["withheld"]["fiscal_years"] == []


class TestAnEmptyTableAndAFullyWithheldTableAreDifferent:
    """"database_empty" is a claim about the database, and it must be true.

    Gating introduces a case that did not exist before: rows are present and
    every one of them is withheld. The pre-existing ``not rows`` branch answers
    ``data_source: "database_empty"`` and ``source: "Run seeder: ..."``. Told
    that, an operator re-runs a seeder that will change nothing, because the
    seeder is not the problem — the rows are there, they just cite no page.

    A gate that hides a figure has to say why in a way a reader can act on. So
    must a gate that hides all of them.
    """

    def test_a_genuinely_empty_table_still_says_so(self, db_session, client):
        body = client.get("/api/v1/fiscal/summary").json()
        assert body["data_source"] == "database_empty"
        assert body["withheld"]["count"] == 0

    def test_rows_present_but_all_withheld_is_not_called_empty(
        self, db_session, client
    ):
        from models import FiscalSummary

        for fy, budget in FY_NO_LOCATOR_WITH_FIGURE.items():
            db_session.add(
                FiscalSummary(
                    fiscal_year=fy, appropriated_budget=budget, unit="KES",
                    page_ref=None,
                )
            )
        db_session.commit()

        body = client.get("/api/v1/fiscal/summary").json()
        assert body["data_source"] != "database_empty", (
            "five rows are in the table; calling that an empty database sends "
            "an operator to re-run a seeder that will not help"
        )
        assert body["withheld"]["count"] == 5
        assert "seed" not in (body["source"] or "").lower(), (
            f"the remedy offered is wrong for this cause: {body['source']!r}"
        )

    def test_it_names_the_withheld_years_even_when_nothing_is_published(
        self, db_session, client
    ):
        from models import FiscalSummary

        for fy, budget in FY_NO_LOCATOR_WITH_FIGURE.items():
            db_session.add(
                FiscalSummary(
                    fiscal_year=fy, appropriated_budget=budget, unit="KES",
                    page_ref=None,
                )
            )
        db_session.commit()

        body = client.get("/api/v1/fiscal/summary").json()
        assert set(body["withheld"]["fiscal_years"]) == set(FY_NO_LOCATOR_WITH_FIGURE)


#: A row the EXISTING completeness filters admit and Tier B refuses: four
#: populated money fields and no page reference. No such row is in production
#: today — which is exactly why a test that only replays today's data would be
#: vacuous. Every published series filter in `main.py` asks "does this row have
#: at least 3 of 4 fields?", a question about substance. None asks whether the
#: figure can be traced. The two rules coincide on today's 29 rows and diverge
#: on this one, and the next COB quarterly write is how it arrives.
COMPLETE_BUT_UNSOURCED = "FY 2016/17"


def _seed_complete_but_unsourced(db_session):
    from models import FiscalSummary

    db_session.add(
        FiscalSummary(
            fiscal_year=COMPLETE_BUT_UNSOURCED,
            appropriated_budget=2_600_000_000_000,
            total_revenue=1_430_000_000_000,
            total_borrowing=650_000_000_000,
            county_allocation=234_000_000_000,
            debt_service_cost=900_000_000_000,
            recurrent_spending=1_700_000_000_000,
            development_spending=900_000_000_000,
            unit="KES",
            page_ref=None,
        )
    )
    db_session.commit()


class TestEveryReadSiteAppliesTheGate:
    """One table, one rule, at every site that publishes from it.

    The module docstring of ``services/publication_gate.py`` records what
    happens otherwise: Stage 0 gated the router only, and
    ``/api/v1/audits/federal`` in ``main.py`` went on serving KES 3.313T of
    withheld rows as ``total_amount_in_findings``. ``fiscal_summaries`` has
    seven read sites in ``main.py``.

    Each test seeds the five sourced years plus one complete-but-unsourced
    year, so it fails for the right reason: not "the row was already excluded
    by a completeness rule" but "the gate is not applied here".
    """

    def test_fiscal_summary_history(self, db_session, client):
        _seed_production_shape(db_session)
        _seed_complete_but_unsourced(db_session)
        body = client.get("/api/v1/fiscal/summary").json()
        assert COMPLETE_BUT_UNSOURCED not in {r["fiscal_year"] for r in body["history"]}

    def test_budget_overview_fiscal_history(self, db_session, client):
        _seed_production_shape(db_session)
        _seed_complete_but_unsourced(db_session)
        body = client.get("/api/v1/budget/overview").json()
        served = {r["fiscal_year"] for r in body.get("fiscal_history") or []}
        assert COMPLETE_BUT_UNSOURCED not in served, (
            "/api/v1/budget/overview publishes a fiscal year that cites no page"
        )

    def test_national_fiscal_outturns_series(self, db_session, client):
        _seed_production_shape(db_session)
        _seed_complete_but_unsourced(db_session)
        body = client.get("/api/v1/dashboards/national/fiscal-outturns").json()
        served = {r.get("period") for r in body.get("series") or []}
        assert COMPLETE_BUT_UNSOURCED not in served, (
            "the national fiscal-outturns series publishes an untraceable year"
        )

    def test_audits_fiscal_years_list(self, db_session, client):
        """The year selector must not offer a year whose figures are withheld."""
        _seed_production_shape(db_session)
        _seed_complete_but_unsourced(db_session)
        body = client.get("/api/v1/audits/fiscal-years").json()
        offered = set(body.get("data") or [])
        if not offered:
            pytest.skip("this path falls back to fiscal_summaries only when "
                        "fiscal_periods is empty; nothing to assert here")
        assert COMPLETE_BUT_UNSOURCED not in offered


class TestTheLatestRowIsGatedToo:
    """`.first()` on fiscal_year DESC is a publication decision like any other.

    Three sites take the newest row and publish figures off it — the national
    per-capita budget (`/api/v1/budget/enhanced`), the civic-figures panel and
    the debt-sustainability ratios. Today the newest row is FY2026/27, which
    carries a locator, so these are no-ops. They are not no-ops the first time
    a newer row lands without one — and a newer row landing without one is the
    ordinary case, because `page_ref` is written by hand.
    """

    def _seed_newest_unsourced(self, db_session):
        from models import FiscalSummary

        _seed_production_shape(db_session)
        db_session.add(
            FiscalSummary(
                fiscal_year="FY 2027/28",
                appropriated_budget=5_900_000_000_000,
                total_revenue=3_100_000_000_000,
                total_borrowing=1_200_000_000_000,
                county_allocation=420_000_000_000,
                debt_service_cost=2_400_000_000_000,
                unit="KES",
                page_ref=None,
            )
        )
        db_session.commit()

    def test_fiscal_summary_current_is_the_newest_SOURCED_year(
        self, db_session, client
    ):
        self._seed_newest_unsourced(db_session)
        body = client.get("/api/v1/fiscal/summary").json()
        assert body["current"]["fiscal_year"] == "FY 2026/27", (
            "the headline moved to a year that cites no page"
        )

    def test_budget_enhanced_does_not_headline_an_unsourced_year(
        self, db_session, client
    ):
        self._seed_newest_unsourced(db_session)
        body = client.get("/api/v1/budget/enhanced").json()

        def _find(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "fiscal_year" and v == "FY 2027/28":
                        return True
                    if _find(v):
                        return True
            elif isinstance(o, list):
                return any(_find(v) for v in o)
            return False

        assert not _find(body), (
            "/api/v1/budget/enhanced headlines FY 2027/28, which cites no page"
        )

    def test_debt_sustainability_does_not_use_an_unsourced_year(
        self, db_session, client
    ):
        self._seed_newest_unsourced(db_session)
        body = client.get("/api/v1/debt/sustainability").json()
        assert "FY 2027/28" not in json_dumps_compact(body), (
            "/api/v1/debt/sustainability reads an untraceable fiscal row"
        )


def json_dumps_compact(obj) -> str:
    import json

    return json.dumps(obj, default=str)


class TestTheOutturnsFallbackNamesTheRightCause:
    """"Run ETL pipeline" is a remedy, and it must match the cause.

    ``/api/v1/dashboards/national/fiscal-outturns`` falls back when the DB
    yields no series. Gating created a new way to reach that fallback — rows
    present, all withheld — where re-running the ETL changes nothing, because
    the rows are already there and simply cite no page.

    The fallback itself is honest about values (`revenue: None`, not 0). This
    is about the sentence next to them.
    """

    def test_it_does_not_blame_the_etl_for_a_provenance_gap(
        self, db_session, client
    ):
        from models import FiscalSummary

        for fy, budget in FY_NO_LOCATOR_WITH_FIGURE.items():
            db_session.add(
                FiscalSummary(
                    fiscal_year=fy,
                    appropriated_budget=budget,
                    total_revenue=budget * 0.55,
                    recurrent_spending=budget * 0.6,
                    development_spending=budget * 0.3,
                    unit="KES",
                    page_ref=None,
                )
            )
        db_session.commit()

        body = client.get("/api/v1/dashboards/national/fiscal-outturns").json()
        blob = json_dumps_compact(body).lower()
        assert "run etl" not in blob, (
            "the rows are present and withheld for want of a page reference; "
            f"re-running the ETL will not add one. Got: {body}"
        )
        assert body.get("withheld", {}).get("count") == 5
        assert set(body["withheld"]["fiscal_years"]) == set(FY_NO_LOCATOR_WITH_FIGURE)

    def test_a_truly_empty_table_still_points_at_the_etl(self, db_session, client):
        """The original remedy must survive for the case it was written for."""
        body = client.get("/api/v1/dashboards/national/fiscal-outturns").json()
        assert body.get("withheld", {}).get("count") == 0


class TestTheDisclosureSurvivesTheNoDatabasePath:
    """The fallback runs when there is no database, and must not crash there.

    The disclosure is computed inside `with next(get_db())`, and consumed after
    the `except`. When `DATABASE_AVAILABLE` is false that assignment never
    happens, so the fallback reads an unbound name — and because the read is
    outside the `except`, the NameError is not caught and the endpoint 500s.
    A gate that takes an endpoint down when the database is absent is worse
    than the silence it replaced.
    """

    def test_it_answers_without_a_database(self, monkeypatch, client):
        import main

        monkeypatch.setattr(main, "DATABASE_AVAILABLE", False)
        resp = client.get("/api/v1/dashboards/national/fiscal-outturns")
        assert resp.status_code == 200, resp.text
        assert resp.json()["withheld"]["count"] == 0

    def test_it_answers_when_the_query_raises(self, monkeypatch, client):
        """The `except` catches the DB error; the fallback must still be safe."""
        import main

        def _boom():
            raise RuntimeError("pool exhausted")

        monkeypatch.setattr(main, "get_db", _boom)
        resp = client.get("/api/v1/dashboards/national/fiscal-outturns")
        assert resp.status_code == 200, resp.text
        assert resp.json()["withheld"]["count"] == 0
