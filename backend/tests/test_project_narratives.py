"""Bounded source observations, through the real parser, writer and reader."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from seeding.domains.stalled_projects import cob_parser as cp, writer
from services.stalled_projects import build_stalled_projects_block

FX = json.loads(
    (Path(__file__).parent / "fixtures/cob_cbirr/narratives_fy2025_26.json").read_text()
)


def source_pages():
    pages = [""] * 935
    pages[0] = "COUNTY GOVERNMENTS FINANCIAL YEAR 2025/26 AUGUST 2026"
    pages[684] = "3.34 Nyamira County 3.34.1 Introduction"
    pages[685] = (
        "Source: Nyamira County Treasury\n"
        + FX["evidence"]["nyamira-summary"]["excerpt"]
        + "\n"
        + FX["evidence"]["nyamira-named"]["excerpt"]
        + "\n3.34.16 Budget Performance by Department"
    )
    pages[756] = "3.38 Siaya County 3.38.1 Introduction"
    pages[757] = (
        "Source: Siaya County Treasury\n"
        + FX["evidence"]["siaya-named"]["excerpt"]
        + "\n3.38.16 Budget Performance by Department"
    )
    return pages


def parse(monkeypatch, tmp_path, pages=None, sha=None):
    import pdfplumber

    path = tmp_path / "edition.pdf"
    path.write_bytes(b"synthetic PDF extraction boundary")
    monkeypatch.setattr(cp, "page_texts", lambda p: pages if pages is not None else source_pages())
    monkeypatch.setattr(
        cp,
        "_source_sha256",
        lambda p: sha if sha is not None else FX["source"]["sha256"],
        raising=False,
    )

    class PDF:
        pages = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(pdfplumber, "open", lambda p: PDF())
    return cp.CbirrStalledProjectsParser(path).parse()


def blocks(monkeypatch, tmp_path, **kw):
    records = parse(monkeypatch, tmp_path, **kw)
    edition = dict(
        records[0], url=FX["source"]["url"], sha256=kw.get("sha") or FX["source"]["sha256"]
    )
    return {c["county"]: writer.build_county_block(c, edition) for c in records[1:]}


def test_exact_anchors_reach_both_reader_paths(monkeypatch, tmp_path):
    stored = blocks(monkeypatch, tmp_path)
    ny = build_stalled_projects_block(stored["Nyamira"])
    si = build_stalled_projects_block(stored["Siaya"])
    n = ny["narratives"]["observations"][0]
    assert n["measures"]["paid"]["state"] == "conflicting"
    assert [s["value"] for s in n["measures"]["paid"]["statements"]] == [26650000, 26620000]
    assert n["scalar_measures"]["paid"] is None
    assert n["milestones"][0]["date"]["value"] == "2023-02"
    s = si["narratives"]["observations"][0]
    assert s["implementing_institution"]["state"] == "unknown"
    assert s["scalar_measures"]["paid"] == 3720000
    assert s["scalar_measures"]["estimated_value"] == 1880000
    assert s["status"]["classification"] == "under_investigation"
    assert ny["count"] is si["count"] is None
    assert ny["total_amount_paid"] is si["total_amount_paid"] is None
    row = dict(
        project_name="table control",
        source_url=FX["source"]["url"],
        source_page=686,
        as_of="2026-06-30",
        reported_by=cp.REPORTED_BY,
        estimated_value_kes=0,
        amount_paid_kes=7,
    )
    old = dict(stored["Nyamira"], rows=[row])
    old.pop("narratives")
    new = dict(old, narratives=stored["Nyamira"]["narratives"])
    a, b = build_stalled_projects_block(old), build_stalled_projects_block(new)
    assert {k: v for k, v in b.items() if k != "narratives"} == {
        k: v for k, v in a.items() if k != "narratives"
    }
    assert b["narratives"]["status"] == "accepted"
    assert b["total_contracted_value"] == 0


def test_writer_and_api_preserve_table_count_and_unknown_institution(
    monkeypatch, tmp_path, db_session, seed_country, client
):
    from models import Entity, EntityType

    records = parse(monkeypatch, tmp_path)
    edition = dict(records[0], url=FX["source"]["url"], sha256=FX["source"]["sha256"])
    for i, name in enumerate(("Nyamira", "Siaya"), 841):
        db_session.add(
            Entity(
                id=i,
                country_id=seed_country.id,
                type=EntityType.COUNTY,
                canonical_name=name + " County",
                slug=name.lower(),
                meta={"later": {"preserve": True}},
            )
        )
    db_session.commit()
    assert writer.write(records[1:], edition, db_session)["rows"] == 0
    for i in (841, 842):
        e = db_session.get(Entity, i)
        assert e.meta["later"] == {"preserve": True}
        assert writer._is_current(e.meta)
        out = client.get(f"/api/v1/counties/{i}/comprehensive")
        assert out.status_code == 200
        assert out.json()["stalled_projects"]["narratives"]["status"] == "accepted"


@pytest.mark.parametrize("damage", ["hash", "period", "page", "passage", "chapter", "context"])
def test_changed_source_refuses_without_losing_unrelated_evidence(monkeypatch, tmp_path, damage):
    pages = source_pages()
    sha = None
    if damage == "hash":
        sha = "a" * 64
    elif damage == "period":
        pages[0] += " first quarter"
    elif damage == "page":
        pages[685] = ""
    elif damage == "passage":
        pages[685] = pages[685].replace("26.65", "26.66")
    elif damage == "chapter":
        pages[684] = "3.34 Kisii County 3.34.1 Introduction"
    else:
        pages[685] = pages[685].replace("Source: Nyamira", "Source: Siaya")
    records = parse(monkeypatch, tmp_path, pages, sha)
    # A real captioned table remains accepted even if an optional narrative refuses.
    from test_stalled_projects_pipeline import _county_from_fixture, EDITION_URL

    county = _county_from_fixture("Kericho")
    county["narratives"] = cp.parse_bounded_narratives(
        pages, records[0], sha or FX["source"]["sha256"]
    )["Nyamira"]
    stored = writer.build_county_block(
        county, dict(records[0], url=EDITION_URL, sha256=sha or FX["source"]["sha256"])
    )
    out = build_stalled_projects_block(stored)
    assert out["narratives"]["status"] == "refused"
    assert out["narratives"]["reason"]
    assert out["count"] == 6
    assert out["total_amount_paid"] == pytest.approx(95394674.22)


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {},
        "",
        True,
        1,
        {"schema_version": True},
        {"schema_version": 2},
        {"status": "accepted"},
    ],
)
def test_corrupt_optional_collection_does_not_suppress_table_output(value):
    from test_stalled_projects_pipeline import _county_from_fixture, EDITION_URL, EDITION

    stored = writer.build_county_block(
        _county_from_fixture("Kericho"), dict(EDITION, url=EDITION_URL)
    )
    control = build_stalled_projects_block(stored)
    stored["narratives"] = value
    out = build_stalled_projects_block(stored)
    assert out["narratives"]["status"] == "refused"
    assert {k: v for k, v in out.items() if k != "narratives"} == {
        k: v for k, v in control.items() if k != "narratives"
    }


@pytest.mark.parametrize(
    "damage",
    [
        "schema_bool",
        "source_ref",
        "extra",
        "empty",
        "evidence_ref",
        "date",
        "date_precision",
        "institution",
        "county",
        "unit",
        "paid_as_payable",
        "no_conflict",
        "selected_winner",
        "bool",
        "nan",
        "inf",
        "negative",
        "zero",
        "progress",
        "milestone_day",
        "status_verified",
        "duplicate",
        "unknown_state",
    ],
)
def test_shaped_changes_are_not_source_authority(monkeypatch, tmp_path, damage):
    stored = blocks(monkeypatch, tmp_path)["Nyamira"]
    corpus = stored["narratives"]["corpus"]
    o = corpus["observations"][0]
    p = o["measures"]["paid"]["statements"][0]
    if damage == "schema_bool":
        corpus["schema_version"] = True
    elif damage == "source_ref":
        o["source_ref"] = "invented"
    elif damage == "extra":
        o["oag_verified"] = True
    elif damage == "empty":
        corpus["observations"] = []
    elif damage == "evidence_ref":
        p["evidence_ref"] = "missing"
    elif damage == "date":
        p["as_of"]["value"] = "2026-02-30"
    elif damage == "date_precision":
        p["as_of"]["precision"] = "month"
    elif damage == "institution":
        o["implementing_institution"]["value"] = "Nyamira County Executive"
    elif damage == "county":
        o["county"]["official_code"] = "041"
    elif damage == "unit":
        p["source_unit"] = "KES"
    elif damage == "paid_as_payable":
        o["measures"]["payable"] = copy.deepcopy(o["measures"]["paid"])
        o["measures"]["paid"] = {"state": "absent", "statements": [], "reason": "not paid"}
    elif damage == "no_conflict":
        o["measures"]["paid"]["state"] = "stated"
    elif damage == "selected_winner":
        o["measures"]["paid"]["statements"] = [p]
    elif damage == "progress":
        o["measures"]["completion_pct"]["statements"][0]["value"] = 101
    elif damage == "milestone_day":
        o["milestones"][0]["date"] = {"value": "2023-02-01", "precision": "day", "reason": None}
    elif damage == "status_verified":
        o["status"]["classification"] = "oag_verified"
    elif damage == "duplicate":
        corpus["observations"].append(copy.deepcopy(o))
    elif damage == "unknown_state":
        o["measures"]["paid"]["state"] = []
    else:
        p["value"] = {
            "bool": True,
            "nan": float("nan"),
            "inf": float("inf"),
            "negative": -1,
            "zero": 0,
        }[damage]
    out = build_stalled_projects_block(stored)
    assert out["narratives"]["status"] == "refused"
    assert out["narratives"]["observations"] == []
    assert (
        writer.build_county_block(
            {"county": "Nyamira", "narratives": stored["narratives"]}, stored["source"]
        )["narratives"]["status"]
        == "refused"
    )


def test_narrow_decimal_conversion_keeps_zero_and_rejects_hostile_values():
    at = cp._narrative_date("2026-06-30")
    assert (
        cp._narrative_statement("0.00", "KES_million", "printed-zero", "named_project", at)["value"]
        == 0
    )
    assert (
        cp._narrative_statement("26.65", "KES_million", "paid", "named_project", at)["value"]
        == 26650000
    )
    for literal in (True, 0, None, "NaN", "inf", "-1", "3,490.800.00"):
        with pytest.raises(ValueError):
            cp._narrative_statement(literal, "KES", "r", "named_project", at)
    for d, p in (
        ("2026-02-30", "day"),
        ("2026-13", "month"),
        ("2026-6-30", "day"),
        (True, "day"),
        ("2026-06-30", "year"),
    ):
        with pytest.raises(ValueError):
            cp._narrative_date(d, p)


def test_legacy_cleanup_and_later_metadata_survive(monkeypatch, tmp_path, db_session, seed_country):
    from models import Entity, EntityType

    old = dict(
        schema=2, rows=[], source={"url": "https://cob.go.ke/old"}, extension={"later": 2026}
    )
    e = Entity(
        id=843,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nyamira County",
        slug="nyamira",
        meta={"stalled_projects": old, "stalled_projects_count": 1, "later": {"preserve": True}},
    )
    db_session.add(e)
    db_session.commit()
    writer.clear_owned_keys(db_session, legacy_only=True)
    db_session.refresh(e)
    assert e.meta["stalled_projects"] == old
    records = parse(monkeypatch, tmp_path)
    edition = dict(records[0], url=FX["source"]["url"], sha256=FX["source"]["sha256"])
    writer.write([c for c in records[1:] if c["county"] == "Nyamira"], edition, db_session)
    db_session.refresh(e)
    assert e.meta["stalled_projects"]["extension"] == {"later": 2026}
    assert e.meta["later"] == {"preserve": True}
    writer.clear_owned_keys(db_session, legacy_only=True)
    assert e.meta["stalled_projects"]["narratives"]["status"] == "accepted"
    # The next non-approved edition must not carry forward an old accepted observation.
    writer.write([{"county": "Nyamira"}], dict(edition, sha256="b" * 64), db_session)
    db_session.refresh(e)
    assert "narratives" not in e.meta["stalled_projects"]
    assert e.meta["stalled_projects"]["extension"] == {"later": 2026}


def test_parse_cache_reuses_then_invalidates_actual_parser_source(monkeypatch, tmp_path):
    import importlib.util
    import sys
    from seeding.domains.stalled_projects import fetcher
    from seeding.parse_cache import parser_digest
    import pdfplumber

    module_path = tmp_path / "owned_parser.py"
    module_path.write_text(Path(cp.__file__).read_text())
    spec = importlib.util.spec_from_file_location("round14_owned_parser", module_path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    module.page_texts = lambda p: source_pages()
    module._source_sha256 = lambda p: FX["source"]["sha256"]

    class PDF:
        pages = []

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr(pdfplumber, "open", lambda p: PDF())
    monkeypatch.setattr(cp, "CbirrStalledProjectsParser", module.CbirrStalledProjectsParser)
    path = tmp_path / "source.pdf"
    path.write_bytes(b"cached-extraction-boundary")
    settings = SimpleNamespace(cache_path=tmp_path / "cache", parse_cache_enabled=True)
    first = fetcher.parse_edition(path, settings)
    old_digest = parser_digest(module.CbirrStalledProjectsParser.parse)
    module.page_texts = lambda p: (_ for _ in ()).throw(AssertionError("cache hit must not parse"))
    assert fetcher.parse_edition(path, settings) == first
    # Change a helper's source on the owned copy, not shared repository code.
    module_path.write_text(module_path.read_text() + "\n# owned helper revision\n")
    assert parser_digest(module.CbirrStalledProjectsParser.parse) != old_digest
    with pytest.raises(AssertionError, match="must not parse"):
        fetcher.parse_edition(path, settings)
    module.page_texts = lambda p: source_pages()
    assert fetcher.parse_edition(path, settings) == first
    path.write_bytes(b"changed source bytes")
    module._source_sha256 = lambda p: "b" * 64
    changed = fetcher.parse_edition(path, settings)
    assert all(c["narratives"]["status"] == "refused" for c in changed[1:])


def test_api_rejects_an_observation_transplanted_to_another_county(
    monkeypatch, tmp_path, db_session, seed_country, client
):
    from models import Entity, EntityType

    stored = blocks(monkeypatch, tmp_path)["Nyamira"]
    e = Entity(
        id=844,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Siaya County",
        slug="siaya",
        meta={"stalled_projects": stored},
    )
    db_session.add(e)
    db_session.commit()
    out = client.get("/api/v1/counties/844/comprehensive")
    assert out.status_code == 200
    projection = out.json()["stalled_projects"]["narratives"]
    assert projection["status"] == "refused"
    assert projection["reason"] == "narrative_county_mismatch"


@pytest.mark.parametrize(
    "old,new", [("26.65", "26.6- 5"), ("34.38", "34.3- 8"), ("2026", "202- 6")]
)
def test_numeric_line_breaks_do_not_become_source_authority(monkeypatch, tmp_path, old, new):
    pages = source_pages()
    pages[685] = pages[685].replace(old, new)
    result = cp.parse_bounded_narratives(pages, cp._edition_header(pages), FX["source"]["sha256"])
    assert result["Nyamira"]["status"] == "refused"
    assert result["Nyamira"]["reason"] == "changed_bounded_passage"


def test_deep_corrupt_optional_evidence_keeps_existing_table_output(monkeypatch, tmp_path):
    stored = blocks(monkeypatch, tmp_path)["Nyamira"]
    node = {}
    for _ in range(12000):
        node = {"nested": node}
    stored["narratives"]["corpus"]["unexpected"] = node
    stored["rows"] = [
        dict(
            project_name="control",
            source_url=FX["source"]["url"],
            source_page=686,
            as_of="2026-06-30",
            reported_by=cp.REPORTED_BY,
            amount_paid_kes=0,
        )
    ]
    out = build_stalled_projects_block(stored)
    assert out["count"] == 1 and out["total_amount_paid"] == 0
    assert out["narratives"]["status"] == "refused"
