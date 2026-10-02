"""Execute the captured CPI correction on real disposable PostgreSQL only."""
import copy
import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.exc import DataError
from decimal import Decimal

from models import Base, EconomicIndicator

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "cpi_source_correction", ROOT / "scripts/verification/cpi_source_correction.py"
)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
MANIFEST = (
    ROOT / "docs/operations/2026-09-30-economic-evidence/cpi-correction-proposal.json"
)


@pytest.fixture
def clone():
    raw = os.environ.get("CPI_TEST_POSTGRES_URL")
    pdf_root = os.environ.get("CPI_TEST_PDF_ROOT")
    if not raw or not pdf_root:
        pytest.skip(
            "requires disposable CPI_TEST_POSTGRES_URL and captured CPI_TEST_PDF_ROOT"
        )
    url = make_url(raw)
    if url.host not in {"localhost", "127.0.0.1", "::1"} or not url.database.startswith(
        "codex_cpi_"
    ):
        pytest.fail("requires loopback codex_cpi_* disposable database")
    schema = "cpi_" + uuid4().hex
    admin = create_engine(raw)
    with admin.begin() as c:
        c.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(raw, connect_args={"options": f"-csearch_path={schema}"})
    Base.metadata.create_all(engine)
    with engine.begin() as c:
        c.execute(
            text("ALTER TABLE economic_indicators ADD COLUMN retained_extra jsonb")
        )
        tables = tool.tables_for(c)
        c.execute(
            tables["countries"]
            .insert()
            .values(
                id=1,
                iso_code="KEN",
                name="Kenya",
                currency="KES",
                timezone="Africa/Nairobi",
                default_locale="en_KE",
            )
        )
        manifest = json.loads(MANIFEST.read_text())
        for row in manifest["before_evidence"]["sources"]:
            c.execute(
                tables["source_documents"]
                .insert()
                .values(**tool.db_values(tables["source_documents"], row))
            )
        for row in manifest["before_evidence"]["rows"]:
            row = {**row, "retained_extra": {"original": row["id"]}}
            c.execute(
                tables["economic_indicators"]
                .insert()
                .values(**tool.db_values(tables["economic_indicators"], row))
            )
        # Adjacent identities: preserve sourced annual history, separate WB
        # base, and the shared placeholder used by the population session.
        for i, kind, day, unit in [
            (26, "inflation_rate", "2024-12-31", "percent"),
            (27, "cpi_index", "2024-12-31", "index_2010_100"),
        ]:
            c.execute(
                tables["economic_indicators"]
                .insert()
                .values(
                    id=i,
                    indicator_type=kind,
                    indicator_date=datetime.fromisoformat(day),
                    value=0,
                    unit=unit,
                    source_document_id=1823,
                    metadata={"retained": True},
                    publishable=False,
                    created_at=datetime(2025, 1, 1),
                    retained_extra={"annual": True},
                )
            )
        c.execute(
            text(
                "INSERT INTO population_data(id,year,total_population,source_document_id) VALUES (79,2025,52500000,1823)"
            )
        )
    pdfs = {
        r: Path(pdf_root) / f"knbs-cpi-{suffix}.pdf"
        for r, suffix in [("knbs_jan2025", "jan2025"), ("knbs_dec2024", "dec2024")]
    }
    yield engine, tables, pdfs
    engine.dispose()
    with admin.begin() as c:
        c.execute(text(f"DROP SCHEMA {schema} CASCADE"))
    admin.dispose()


def inventory(clone):
    engine, tables, _ = clone
    with engine.connect() as c:
        result = {
            name: tool.normalized(
                [dict(r) for r in c.execute(select(t).order_by(t.c.id)).mappings()]
            )
            for name, t in tables.items()
        }
        result["population_control"] = tool.normalized(
            dict(
                c.execute(text("SELECT * FROM population_data WHERE id=79"))
                .mappings()
                .one()
            )
        )
        return result


def prepared(clone):
    return tool.run(clone[0], MANIFEST, clone[2])


def apply(clone, tmp_path):
    plan = prepared(clone)
    receipt = tmp_path / "intent.json"
    result = tool.run(
        clone[0],
        MANIFEST,
        clone[2],
        plan=plan,
        expected_sha256=tool.digest(plan),
        commit=True,
        receipt_path=receipt,
    )
    resolved = json.loads(Path(str(receipt) + ".resolved.json").read_text())
    assert result["outcome"] == "committed" and result[
        "recovery_sha256"
    ] == tool.digest(resolved)
    return plan, resolved


def test_prepare_default_apply_and_recovery_are_readonly_then_atomic(clone, tmp_path):
    before = inventory(clone)
    plan = prepared(clone)
    assert plan == prepared(clone)
    assert (
        tool.run(
            clone[0], MANIFEST, clone[2], plan=plan, expected_sha256=tool.digest(plan)
        )["outcome"]
        == "read_only_dry_run"
    )
    assert inventory(clone) == before
    _, receipt = apply(clone, tmp_path)
    after = inventory(clone)
    for key in ["countries", "population_control"]:
        assert after[key] == before[key]
    for row in before["source_documents"]:
        assert row in after["source_documents"]
    for row in before["economic_indicators"]:
        if row["id"] in [26, 27]:
            assert row in after["economic_indicators"]
    assert [
        (r["id"], r["indicator_type"], r["value"], r["unit"], r["publishable"])
        for r in after["economic_indicators"]
        if r["id"] in [67, 86, 87]
    ] == [
        (67, "cpi", "142.68", "index_2019_02_100", True),
        (86, "CPI", "142.68", "index_2019_02_100", True),
        (87, "CPI", "141.66", "index_2019_02_100", True),
    ]
    with Session(clone[0]) as db:
        from routers.economic import get_economic_indicators
        import asyncio

        rows = asyncio.run(
            get_economic_indicators(
                indicator_type=None,
                entity_id=None,
                start_date=None,
                end_date=None,
                min_confidence=0,
                limit=100,
                db=db,
            )
        )
        assert {r.id for r in rows} == {26, 27, 67, 86, 87}
        assert (
            db.get(EconomicIndicator, 67).extraction_id
            == db.get(EconomicIndicator, 86).extraction_id
        )
    kwargs = dict(recover_receipt=receipt, expected_sha256=tool.digest(receipt))
    assert (
        tool.run(clone[0], MANIFEST, clone[2], **kwargs)["outcome"]
        == "read_only_dry_run"
    )
    assert inventory(clone) == after
    assert (
        tool.run(
            clone[0],
            MANIFEST,
            clone[2],
            commit=True,
            receipt_path=tmp_path / "recover.json",
            **kwargs,
        )["outcome"]
        == "committed"
    )
    recovered = inventory(clone)
    assert recovered["economic_indicators"] == before["economic_indicators"]
    assert recovered["source_documents"] == after["source_documents"]
    assert recovered["extractions"] == after["extractions"]
    assert recovered["population_control"] == before["population_control"]
    # Evidence retained by recovery is safely reused by a fresh forward plan.
    next_plan = prepared(clone)
    assert all(next_plan["documents"].values()) and all(
        next_plan["extractions"].values()
    )
    tool.run(
        clone[0],
        MANIFEST,
        clone[2],
        plan=next_plan,
        expected_sha256=tool.digest(next_plan),
        commit=True,
        receipt_path=tmp_path / "reapply.json",
    )
    assert inventory(clone)["economic_indicators"] == after["economic_indicators"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("value", "143.09"),
        ("indicator_type", "cpi"),
        ("unit", "percent"),
        ("metadata", {"drift": True}),
        ("retained_extra", {"drift": True}),
        ("publishable", True),
    ],
)
def test_full_preimage_drift_refuses_all_rows(clone, tmp_path, field, value):
    plan = prepared(clone)
    with clone[0].begin() as c:
        c.execute(
            update(clone[1]["economic_indicators"])
            .where(clone[1]["economic_indicators"].c.id == 86)
            .values(**{field: value})
        )
    before = inventory(clone)
    with pytest.raises(ValueError):
        tool.run(
            clone[0],
            MANIFEST,
            clone[2],
            plan=plan,
            expected_sha256=tool.digest(plan),
            commit=True,
            receipt_path=tmp_path / "refused.json",
        )
    assert inventory(clone) == before
    assert not (tmp_path / "refused.json").exists()


@pytest.mark.parametrize("failure", ["intent_io", "resolved_io", "second_update"])
def test_mid_operation_failure_rolls_back_all_dml_and_preserves_recovery_boundary(
    clone, tmp_path, monkeypatch, failure
):
    plan = prepared(clone)
    before = inventory(clone)
    if failure.endswith("_io"):
        original = tool.save_new

        def fail(path, value):
            if failure == "intent_io" or str(path).endswith(".resolved.json"):
                raise OSError("injected durable receipt failure")
            return original(path, value)

        monkeypatch.setattr(tool, "save_new", fail)
    else:
        with clone[0].begin() as c:
            c.execute(
                text(
                    "CREATE FUNCTION cpi_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.id=86 THEN RAISE EXCEPTION 'injected failure'; END IF; RETURN NEW; END $$"
                )
            )
            c.execute(
                text(
                    "CREATE TRIGGER cpi_failure BEFORE UPDATE ON economic_indicators FOR EACH ROW EXECUTE FUNCTION cpi_fail()"
                )
            )
    with pytest.raises(Exception):
        tool.run(
            clone[0],
            MANIFEST,
            clone[2],
            plan=plan,
            expected_sha256=tool.digest(plan),
            commit=True,
            receipt_path=tmp_path / "failure.json",
        )
    assert inventory(clone) == before
    assert not (tmp_path / "failure.json.resolved.json").exists()
    if failure != "intent_io":
        assert (tmp_path / "failure.json").exists()


@pytest.mark.parametrize(
    "damage",
    [
        "value",
        "extra",
        "source",
        "extraction",
        "forged_before",
        "forged_after",
        "allocation",
    ],
)
def test_recovery_refuses_drift_or_forged_receipt(clone, tmp_path, damage):
    _, receipt = apply(clone, tmp_path)
    if damage in ["value", "extra", "source", "extraction"]:
        with clone[0].begin() as c:
            if damage in ["value", "extra"]:
                c.execute(
                    update(clone[1]["economic_indicators"])
                    .where(clone[1]["economic_indicators"].c.id == 67)
                    .values(
                        **(
                            {"value": 150}
                            if damage == "value"
                            else {"retained_extra": {"changed": True}}
                        )
                    )
                )
            elif damage == "source":
                c.execute(
                    update(clone[1]["source_documents"])
                    .where(
                        clone[1]["source_documents"].c.id
                        == receipt["allocations"]["source_documents"][0]["id"]
                    )
                    .values(md5="f" * 32)
                )
            else:
                c.execute(
                    update(clone[1]["extractions"])
                    .where(
                        clone[1]["extractions"].c.id
                        == receipt["allocations"]["extractions"][0]["id"]
                    )
                    .values(extracted_json={})
                )
    elif damage == "forged_before":
        receipt["plan"]["before"][0]["value"] = "1.00"
        receipt["plan_sha256"] = tool.digest(receipt["plan"])
    elif damage == "forged_after":
        receipt["after"][0]["unit"] = "percent"
    else:
        receipt["allocations"]["extractions"][0]["extracted_json"] = {}
    before = inventory(clone)
    with pytest.raises((ValueError, KeyError)):
        tool.run(
            clone[0],
            MANIFEST,
            clone[2],
            recover_receipt=receipt,
            expected_sha256=tool.digest(receipt),
            commit=True,
            receipt_path=tmp_path / "refused.json",
        )
    assert inventory(clone) == before


@pytest.mark.parametrize(
    "damage", ["source_url_duplicate", "source_conflict", "type_date_duplicate"]
)
def test_ambiguous_identity_refuses_without_allocating(clone, damage):
    manifest = json.loads(MANIFEST.read_text())
    s = clone[1]["source_documents"]
    e = clone[1]["economic_indicators"]
    with clone[0].begin() as c:
        if damage.startswith("source"):
            values = tool.source_values(
                manifest["source_documents_to_allocate_or_reuse"]["knbs_jan2025"]
            )
            if damage == "source_conflict":
                values["md5"] = "f" * 32
            c.execute(s.insert().values(**values))
            if damage == "source_url_duplicate":
                c.execute(s.insert().values(**values))
        else:
            values = tool.db_values(e, manifest["before_evidence"]["rows"][1])
            values["id"] = 888
            c.execute(e.insert().values(**values))
    before = inventory(clone)
    with pytest.raises(ValueError):
        prepared(clone)
    assert inventory(clone) == before


@pytest.mark.parametrize("kind", ["CPI", "cpi", "cpi_index"])
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_postgres_hostile_numeric_values_never_publish(clone, kind, value):
    if value != "NaN":
        # PostgreSQL Numeric(10,2) itself refuses infinities. Do not claim a
        # stored Infinity fixture against a column that cannot hold one.
        with pytest.raises(DataError):
            with clone[0].begin() as c:
                c.execute(
                    text(
                        "UPDATE economic_indicators SET value=CAST(:v AS numeric) WHERE id=67"
                    ),
                    {"v": value},
                )
    else:
        with clone[0].begin() as c:
            c.execute(
                text(
                    "UPDATE economic_indicators SET value=CAST(:v AS numeric), indicator_type=:kind WHERE id=67"
                ),
                {"v": value, "kind": kind},
            )
    with Session(clone[0]) as db:
        row = db.get(EconomicIndicator, 67)
        if value != "NaN":
            row.value = Decimal(value)
            row.indicator_type = kind
        assert tool.economic_publication_failure(row, db) == "non-finite economic value"


def test_missing_bad_pdf_and_manifest_refuse_before_database_mutation(clone, tmp_path):
    before = inventory(clone)
    for raw in [b"", b"not a pdf"]:
        p = tmp_path / "bad.pdf"
        p.write_bytes(raw)
        with pytest.raises(ValueError):
            tool.run(clone[0], MANIFEST, {**clone[2], "knbs_jan2025": p})
    with pytest.raises(FileNotFoundError):
        tool.run(
            clone[0], MANIFEST, {**clone[2], "knbs_jan2025": tmp_path / "absent.pdf"}
        )
    m = json.loads(MANIFEST.read_text())
    m["updates"][0]["after"]["value"] = "1.00"
    altered = tmp_path / "manifest.json"
    altered.write_text(json.dumps(m))
    with pytest.raises(ValueError):
        tool.run(clone[0], altered, clone[2])
    assert inventory(clone) == before


@pytest.mark.parametrize("commit", [1, None, "false"])
def test_direct_call_cannot_bypass_boolean_commit_guard(clone, commit):
    with pytest.raises(ValueError):
        tool.run(clone[0], MANIFEST, clone[2], commit=commit)


def test_next_actual_domain_ingestion_preserves_corrected_cpi_and_shared_source(
    clone, tmp_path, monkeypatch
):
    import importlib
    from seeding.config import SeedingSettings
    from seeding.types import DomainRunContext
    from seeding.domains.economic_indicators import fetcher

    domain = importlib.import_module("seeding.domains.economic_indicators")
    apply(clone, tmp_path)
    before = inventory(clone)

    class Reply:
        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, **kwargs):
            rows = (
                [{"date": "2024", "value": 200}] if url.endswith("/FP.CPI.TOTL") else []
            )
            return Reply([{"page": 1}, rows])

    monkeypatch.setattr(domain, "create_http_client", lambda settings: Client())
    monkeypatch.setattr(
        fetcher, "_fetch_cbk", lambda client: ([], "synthetic absent CBK", [])
    )
    with Session(clone[0]) as db:
        result = domain.run(
            db, SeedingSettings(), DomainRunContext(since=None, dry_run=False)
        )
        db.commit()
        assert result.items_processed > 0
        corrected = [
            r for r in before["economic_indicators"] if r["id"] in [67, 86, 87]
        ]
        with clone[0].connect() as c:
            assert tool.snapshot(c, clone[1], [67, 86, 87]) == corrected
    after = inventory(clone)
    for row in before["source_documents"]:
        assert row in after["source_documents"]
    assert after["population_control"] == before["population_control"]
    assert next(r for r in after["economic_indicators"] if r["id"] == 26) == next(
        r for r in before["economic_indicators"] if r["id"] == 26
    )


def test_concurrent_writer_is_blocked_until_atomic_correction_finishes(
    clone, tmp_path, monkeypatch
):
    from sqlalchemy.exc import OperationalError

    plan = prepared(clone)
    original = tool.save_new
    blocked = []

    def probe(path, value):
        original(path, value)
        if str(path).endswith(".resolved.json"):
            return
        with clone[0].connect() as other:
            with pytest.raises(OperationalError) as exc:
                with other.begin():
                    other.execute(text("SET LOCAL lock_timeout='100ms'"))
                    other.execute(
                        text("UPDATE economic_indicators SET value=1 WHERE id=86")
                    )
            assert exc.value.orig.pgcode == "55P03"
            blocked.append(True)

    monkeypatch.setattr(tool, "save_new", probe)
    tool.run(
        clone[0],
        MANIFEST,
        clone[2],
        plan=plan,
        expected_sha256=tool.digest(plan),
        commit=True,
        receipt_path=tmp_path / "concurrent.json",
    )
    assert blocked == [True]


def test_recovery_receipt_failure_preserves_approved_after_images(
    clone, tmp_path, monkeypatch
):
    _, receipt = apply(clone, tmp_path)
    before = inventory(clone)

    def fail(*args, **kwargs):
        raise OSError("injected recovery durability failure")

    monkeypatch.setattr(tool, "save_new", fail)
    with pytest.raises(OSError):
        tool.run(
            clone[0],
            MANIFEST,
            clone[2],
            recover_receipt=receipt,
            expected_sha256=tool.digest(receipt),
            commit=True,
            receipt_path=tmp_path / "recover-fail.json",
        )
    assert inventory(clone) == before


def test_legacy_etl_loader_cannot_replace_or_publish_corrected_cpi(
    clone, tmp_path, monkeypatch
):
    import asyncio

    spec = importlib.util.spec_from_file_location(
        "session1_legacy_loader", ROOT / "etl/database_loader.py"
    )
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    apply(clone, tmp_path)
    before = inventory(clone)
    loader = legacy.DatabaseLoader.__new__(legacy.DatabaseLoader)

    async def national_scope(*args):
        return None

    monkeypatch.setattr(loader, "ensure_entity_exists", national_scope)
    with Session(clone[0]) as db:
        asyncio.run(
            loader._load_indicator_item(
                db,
                {
                    "indicator_type": "CPI",
                    "period": "2025-01-31",
                    "value": 143.08,
                    "unit": "index",
                },
                1715,
                1,
            )
        )
        candidates = (
            db.query(EconomicIndicator)
            .filter(EconomicIndicator.indicator_type == "CPI")
            .all()
        )
        introduced = next(r for r in candidates if r.id not in [86, 87])
        assert introduced.publishable is False
        assert (
            tool.economic_publication_failure(introduced, db)
            == "CPI not approved for publication"
        )
    after = inventory(clone)
    for row in before["economic_indicators"]:
        assert row in after["economic_indicators"]


def test_all_captured_annual_average_observations_survive_cpi_reconciliation(
    clone, tmp_path
):
    # Selected historical tuples, not recovered full original row preimages.
    selected = json.loads(
        (
            ROOT
            / "backend/tests/fixtures/economic/annual_inflation_selection_2026-09-29.json"
        ).read_text()
    )["rows"]
    e = clone[1]["economic_indicators"]
    s = clone[1]["source_documents"]
    with clone[0].begin() as c:
        c.execute(update(e).where(e.c.id == 27).values(id=90000))
        c.execute(e.delete().where(e.c.id == 26))
        c.execute(
            s.insert().values(
                id=1856,
                country_id=1,
                publisher="World Bank",
                title="Synthetic source row for captured annual tuples",
                url=selected[0]["url"],
                doc_type="REPORT",
                status="AVAILABLE",
                fetch_date=datetime(2026, 9, 29),
                last_seen_at=datetime(2026, 9, 29),
            )
        )
        for row in selected:
            c.execute(
                e.insert().values(
                    id=row["id"],
                    indicator_type="inflation_rate",
                    indicator_date=datetime.fromisoformat(row["observation_date"]),
                    value=row["value"],
                    unit="percent",
                    source_document_id=1856,
                    metadata={
                        "measure": row["measure"],
                        "source_label": row["source_label"],
                    },
                    publishable=False,
                    retained_extra={"captured_tuple_synthetic_remaining_fields": True},
                )
            )
    before = inventory(clone)
    apply(clone, tmp_path)
    after = inventory(clone)
    annual = [
        r
        for r in before["economic_indicators"]
        if r["indicator_type"] == "inflation_rate"
    ]
    assert len(annual) == 11
    assert annual == [
        r
        for r in after["economic_indicators"]
        if r["indicator_type"] == "inflation_rate"
    ]


def test_recovery_refuses_new_duplicate_exact_identity(clone, tmp_path):
    _, receipt = apply(clone, tmp_path)
    values = tool.db_values(clone[1]["economic_indicators"], receipt["after"][1])
    values["id"] = 999
    with clone[0].begin() as c:
        c.execute(clone[1]["economic_indicators"].insert().values(**values))
    before = inventory(clone)
    with pytest.raises(ValueError):
        tool.run(
            clone[0],
            MANIFEST,
            clone[2],
            recover_receipt=receipt,
            expected_sha256=tool.digest(receipt),
            commit=True,
            receipt_path=tmp_path / "duplicate-recovery.json",
        )
    assert inventory(clone) == before


def test_empty_publication_identity_cannot_certify_success(clone):
    with clone[0].connect() as c:
        with pytest.raises(ValueError):
            tool.assert_publication(c, [])


def test_commit_refuses_shared_source_json_type_change(clone, tmp_path):
    with clone[0].begin() as c:
        c.execute(text("ALTER TABLE source_documents ADD COLUMN retained_extra jsonb"))
        c.execute(text(
            "UPDATE source_documents SET retained_extra="
            "jsonb_build_object('verified', true) WHERE id=1823"
        ))
        c.execute(text(
            "CREATE FUNCTION cpi_type_drift() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN IF NEW.id=87 THEN UPDATE source_documents SET retained_extra="
            "jsonb_build_object('verified', 1) WHERE id=1823; END IF; RETURN NEW; END $$"
        ))
        c.execute(text(
            "CREATE TRIGGER cpi_type_drift AFTER UPDATE ON economic_indicators "
            "FOR EACH ROW EXECUTE FUNCTION cpi_type_drift()"
        ))
    with clone[0].connect() as c:
        clone[1].update(tool.tables_for(c))
    plan = prepared(clone)
    before = inventory(clone)
    intent = tmp_path / "type-drift.json"
    with pytest.raises(ValueError, match="original shared source drift"):
        tool.run(
            clone[0], MANIFEST, clone[2], plan=plan,
            expected_sha256=tool.digest(plan), commit=True, receipt_path=intent,
        )
    assert tool.encoded(inventory(clone)) == tool.encoded(before)
    assert intent.exists() and not Path(str(intent) + ".resolved.json").exists()


def test_recovery_refuses_retained_json_numeric_type_change(clone, tmp_path):
    _, receipt = apply(clone, tmp_path)
    with clone[0].begin() as c:
        c.execute(
            update(clone[1]["economic_indicators"])
            .where(clone[1]["economic_indicators"].c.id == 67)
            .values(retained_extra={"original": 67.0})
        )
    before = inventory(clone)
    intent = tmp_path / "numeric-type-recovery.json"
    with pytest.raises(ValueError, match="recovery full after-image drift"):
        tool.run(
            clone[0], MANIFEST, clone[2], recover_receipt=receipt,
            expected_sha256=tool.digest(receipt), commit=True, receipt_path=intent,
        )
    assert tool.encoded(inventory(clone)) == tool.encoded(before)
    assert not intent.exists()


@pytest.mark.parametrize(
    "table,target", [("source_documents", 1823), ("countries", 1), ("extractions", None)]
)
def test_recovery_rolls_back_protected_context_changed_by_inverse(
    clone, tmp_path, table, target
):
    with clone[0].begin() as c:
        c.execute(text(
            f"ALTER TABLE {table} ADD COLUMN retained_context jsonb "
            "DEFAULT jsonb_build_object('guard', false)"
        ))
    with clone[0].connect() as c:
        clone[1].update(tool.tables_for(c))
    _, receipt = apply(clone, tmp_path)
    if target is None:
        target = receipt["allocations"]["extractions"][0]["id"]
    with clone[0].begin() as c:
        c.execute(text(
            "CREATE FUNCTION cpi_inverse_context() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN IF NEW.id=87 AND NEW.unit='index' THEN "
            f"UPDATE {table} SET retained_context=jsonb_build_object('guard', 0) "
            f"WHERE id={target}; END IF; RETURN NEW; END $$"
        ))
        c.execute(text(
            "CREATE TRIGGER cpi_inverse_context AFTER UPDATE ON economic_indicators "
            "FOR EACH ROW EXECUTE FUNCTION cpi_inverse_context()"
        ))
    before = inventory(clone)
    intent = tmp_path / "inverse-context.json"
    with pytest.raises(ValueError, match="context drift|source drift|allocated evidence drift"):
        tool.run(
            clone[0], MANIFEST, clone[2], recover_receipt=receipt,
            expected_sha256=tool.digest(receipt), commit=True, receipt_path=intent,
        )
    assert tool.encoded(inventory(clone)) == tool.encoded(before)
    assert intent.exists()


@pytest.mark.parametrize(
    "table,reference", [("source_documents", "source_document_id"), ("extractions", "extraction_id")]
)
def test_commit_rolls_back_allocated_context_changed_by_updates(
    clone, tmp_path, table, reference
):
    with clone[0].begin() as c:
        c.execute(text(
            f"ALTER TABLE {table} ADD COLUMN retained_context jsonb "
            "DEFAULT jsonb_build_object('guard', false)"
        ))
        c.execute(text(
            "CREATE FUNCTION cpi_forward_context() RETURNS trigger LANGUAGE plpgsql AS $$ "
            "BEGIN IF NEW.id=87 THEN "
            f"UPDATE {table} SET retained_context=jsonb_build_object('guard', 0) "
            f"WHERE id=NEW.{reference}; END IF; RETURN NEW; END $$"
        ))
        c.execute(text(
            "CREATE TRIGGER cpi_forward_context AFTER UPDATE ON economic_indicators "
            "FOR EACH ROW EXECUTE FUNCTION cpi_forward_context()"
        ))
    with clone[0].connect() as c:
        clone[1].update(tool.tables_for(c))
    plan = prepared(clone)
    before = inventory(clone)
    intent = tmp_path / "forward-context.json"
    with pytest.raises(ValueError, match="postwrite allocated evidence drift"):
        tool.run(
            clone[0], MANIFEST, clone[2], plan=plan,
            expected_sha256=tool.digest(plan), commit=True, receipt_path=intent,
        )
    assert tool.encoded(inventory(clone)) == tool.encoded(before)
    assert intent.exists() and not Path(str(intent) + ".resolved.json").exists()


@pytest.mark.parametrize("damage", ["omitted", "replaced"])
@pytest.mark.parametrize("commit", [False, True])
def test_rehashed_recovery_cannot_discard_reviewed_shared_source_context(
    clone, tmp_path, damage, commit
):
    _, receipt = apply(clone, tmp_path)
    source_id = receipt["plan"]["original_sources"][0]["id"]
    source = clone[1]["source_documents"]
    with clone[0].begin() as c:
        c.execute(
            update(source).where(source.c.id == source_id).values(
                title="synthetic intervening source title"
            )
        )
    before = inventory(clone)
    # The intact receipt detects this drift. Rehashing a replacement receipt
    # must not make the manifest's original shared-source requirements optional.
    with pytest.raises(ValueError, match="source drift"):
        tool.run(
            clone[0], MANIFEST, clone[2], recover_receipt=receipt,
            expected_sha256=tool.digest(receipt),
        )
    if damage == "omitted":
        receipt["plan"]["original_sources"] = []
    else:
        receipt["plan"]["original_sources"][0] = next(
            row for row in before["source_documents"] if row["id"] == source_id
        )
    receipt["plan_sha256"] = tool.digest(receipt["plan"])
    intent = tmp_path / "rehashed-inverse.json"
    with pytest.raises(ValueError):
        tool.run(
            clone[0], MANIFEST, clone[2], recover_receipt=receipt,
            expected_sha256=tool.digest(receipt), commit=commit,
            receipt_path=intent,
        )
    assert tool.encoded(inventory(clone)) == tool.encoded(before)
    assert not intent.exists()
