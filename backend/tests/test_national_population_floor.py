"""82 is not a national population, at the writer and in the table.

Companion to test_population_map_and_national_fallback.py. That file is about
what reads population_data; this one is about what puts 82 in it and what takes
it back out (issue #190).

population_data id=69 — National Government, year 2026, total_population 82,
written 2026-03-01 06:00:16 with confidence 1.00 and no source_document_id —
survived alembic ``f4a1c07b9e52`` by design: its year IS a calendar year and it
is not a county, so neither of that migration's rules touches it.

The rule here is scope-based rather than id-based, for the same reason
``f4a1c07b9e52`` gave: it has to say what is wrong with the row, not where the
row came from.

    A population row that is national in scope — ``entity_id IS NULL`` or
    attached to an entity of type NATIONAL — below 5,000,000 is not a national
    population.

Kenya's 1948 census counted 5.4 million. County rows are untouched: all 47 on
production sit below that floor (Lamu, 143,920, is the smallest), which is why
the floor is scoped to national rows rather than applied to the column.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from typing import Iterator

import pytest
from models import Base, Country, Entity, EntityType, PopulationData
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - dialect shim
    return "TEXT"


_VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
_MIGRATION = "a2f7c1b48d90_a_national_population_of_82"

NATIONAL_2019 = 47_564_296  # id=64, source_document 1823
WORLD_BANK_2025 = 57_532_493  # id=85, the series /population/latest serves
ID_69 = 82
LAMU_2019 = 143_920  # the smallest county row on production
NAIROBI_2019 = 4_397_073  # the largest


class _RecordingOp:
    """``alembic.op``, but ``get_bind()`` hands back a real connection.

    The migration's decision is a DELETE, so recording the SQL string would
    assert the implementation. This runs it.
    """

    def __init__(self, connection):
        self._connection = connection
        self.constraints: list[tuple] = []

    def get_bind(self):
        return self._connection

    def create_check_constraint(self, name, table, condition, **kw):
        self.constraints.append((name, table, str(condition)))

    def drop_constraint(self, name, table, **kw):
        self.constraints = [c for c in self.constraints if c[0] != name]


def _revision_graph() -> dict:
    """{revision: (stem, down_revision)} for every migration on disk."""
    graph = {}
    for path in _VERSIONS.glob("*.py"):
        text_ = path.read_text()
        rev = down = None
        for line in text_.splitlines():
            if line.startswith("revision = "):
                rev = line.split("=", 1)[1].strip().strip("\"'")
            elif line.startswith("down_revision = "):
                raw = line.split("=", 1)[1].strip()
                down = None if raw == "None" else raw.strip("\"'")
        if rev:
            graph[rev] = (path.stem, down)
    return graph


def _chain_to_head() -> list:
    """Migration stems from root to head, in application order."""
    graph = _revision_graph()
    parents = {down for _, down in graph.values() if down}
    heads = [rev for rev in graph if rev not in parents]
    assert len(heads) == 1, f"expected a single alembic head, found {heads}"

    chain, cursor = [], heads[0]
    while cursor is not None:
        stem, down = graph[cursor]
        chain.append(stem)
        cursor = down
    return list(reversed(chain))


def _load_named(stem: str, recorder: _RecordingOp):
    path = _VERSIONS / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(f"_mig_{stem}", path)
    module = importlib.util.module_from_spec(spec)
    fake_alembic = types.ModuleType("alembic")
    fake_alembic.op = recorder
    saved = sys.modules.get("alembic")
    sys.modules["alembic"] = fake_alembic
    try:
        spec.loader.exec_module(module)
    finally:
        if saved is not None:
            sys.modules["alembic"] = saved
        else:
            del sys.modules["alembic"]
    module.op = recorder
    return module


def _load_migration(recorder: _RecordingOp):
    return _load_named(_MIGRATION, recorder)


@pytest.fixture()
def db(tmp_path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path/'floor.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _country(session: Session) -> Country:
    country = Country(
        name="Kenya",
        iso_code="KE",
        currency="KES",
        timezone="Africa/Nairobi",
        default_locale="en-KE",
    )
    session.add(country)
    session.flush()
    return country


def _entity(session: Session, name: str, kind: EntityType) -> Entity:
    entity = Entity(
        country_id=session.query(Country).first().id,
        canonical_name=name,
        slug=name.lower().replace(" ", "-"),
        type=kind,
    )
    session.add(entity)
    session.flush()
    return entity


def _production_shape(session: Session) -> None:
    """The four row kinds production holds, one of each."""
    _country(session)
    national = _entity(session, "National Government", EntityType.NATIONAL)
    lamu = _entity(session, "Lamu", EntityType.COUNTY)
    nairobi = _entity(session, "Nairobi", EntityType.COUNTY)

    session.add_all(
        [
            # id=64: the census figure, kept.
            PopulationData(
                entity_id=national.id,
                year=2019,
                total_population=NATIONAL_2019,
                source_document_id=1823,
            ),
            # id=69: the row this migration removes.
            PopulationData(entity_id=national.id, year=2026, total_population=ID_69),
            # id=85: the entity_id IS NULL series, kept.
            PopulationData(entity_id=None, year=2025, total_population=WORLD_BANK_2025),
            # County rows sit far below the floor and must be untouched.
            PopulationData(entity_id=lamu.id, year=2019, total_population=LAMU_2019),
            PopulationData(
                entity_id=nairobi.id, year=2019, total_population=NAIROBI_2019
            ),
        ]
    )
    session.commit()


def _upgrade(session: Session) -> _RecordingOp:
    recorder = _RecordingOp(session.connection())
    _load_migration(recorder).upgrade()
    session.commit()
    return recorder


class TestTheChainLeavesNoImplausibleNationalRow:
    """Stated against the migration HEAD, not against one file.

    This is the assertion that was red on ``origin/main``: the head there is
    ``f4a1c07b9e52``, whose two rules explicitly do not reach id=69 — its own
    docstring says so — so the chain ended with an 82 still in the table. It
    stays honest if this migration is ever superseded, and it fails if a later
    one reintroduces the row.
    """

    def test_no_national_scope_row_below_the_floor_survives_the_chain(self, db):
        _production_shape(db)

        recorder = _RecordingOp(db.connection())
        for stem in _chain_to_head():
            source = (_VERSIONS / f"{stem}.py").read_text()
            # Only the migrations that remove population rows are relevant, and
            # only they are safe to run against this fixture's schema — the rest
            # of the chain does DDL that create_all() has already applied.
            if "DELETE FROM population_data" not in source:
                continue
            _load_named(stem, recorder).upgrade()
        db.commit()

        offenders = [
            (p.entity_id, p.year, p.total_population)
            for p, e in db.query(PopulationData, Entity)
            .outerjoin(Entity, PopulationData.entity_id == Entity.id)
            .all()
            if (p.entity_id is None or e.type == EntityType.NATIONAL)
            and p.total_population < 5_000_000
        ]
        assert offenders == [], (
            f"the migration chain leaves national-scope rows below 5,000,000: "
            f"{offenders} — 82 is not a national population"
        )


class TestMigrationRemovesTheRow:
    def test_the_previous_migration_left_this_row_behind(self, db):
        """Why this migration exists, asserted rather than asserted-about.

        ``f4a1c07b9e52`` deletes on two rules: year outside 1900-2100, and a
        COUNTY row above 6,000,000. id=69's year is 2026 and it is not a county.
        """
        _production_shape(db)

        recorder = _RecordingOp(db.connection())
        _load_named("f4a1c07b9e52_a_year_column_must_hold_a_year", recorder).upgrade()
        db.commit()

        assert ID_69 in {p.total_population for p in db.query(PopulationData).all()}

    def test_it_removes_the_national_row_below_the_floor(self, db):
        _production_shape(db)

        _upgrade(db)

        survivors = {
            (p.entity_id, p.year, p.total_population)
            for p in db.query(PopulationData).all()
        }
        assert ID_69 not in {pop for _, _, pop in survivors}

    def test_national_government_keeps_its_census_figure(self, db):
        """This corrects a number; it must not blank one."""
        _production_shape(db)
        national_id = (
            db.query(Entity).filter(Entity.type == EntityType.NATIONAL).one().id
        )

        _upgrade(db)

        kept = db.query(PopulationData).filter_by(entity_id=national_id).all()
        assert [(p.year, p.total_population, p.source_document_id) for p in kept] == [
            (2019, NATIONAL_2019, 1823)
        ]

    def test_county_rows_are_untouched(self, db):
        """All 47 production county rows are below 5,000,000 by construction."""
        _production_shape(db)

        _upgrade(db)

        counties = (
            db.query(PopulationData)
            .join(Entity, PopulationData.entity_id == Entity.id)
            .filter(Entity.type == EntityType.COUNTY)
            .all()
        )
        assert sorted(p.total_population for p in counties) == [
            LAMU_2019,
            NAIROBI_2019,
        ]

    def test_the_null_entity_series_is_untouched(self, db):
        _production_shape(db)

        _upgrade(db)

        series = db.query(PopulationData).filter(PopulationData.entity_id.is_(None)).all()
        assert [(p.year, p.total_population) for p in series] == [(2025, WORLD_BANK_2025)]

    def test_replaying_on_a_clean_database_removes_nothing(self, db):
        _production_shape(db)
        _upgrade(db)
        before = db.query(PopulationData).count()

        _upgrade(db)

        assert db.query(PopulationData).count() == before

    def test_the_constraint_binds_the_null_entity_series(self, db):
        """The half of the rule a CHECK can express."""
        _production_shape(db)

        recorder = _upgrade(db)

        names = [name for name, _, _ in recorder.constraints]
        assert "ck_population_data_national_series_is_plausible" in names
        condition = next(
            cond for name, _, cond in recorder.constraints if "plausible" in name
        )
        assert "entity_id IS NOT NULL" in condition
        assert "5000000" in condition

    def test_downgrade_drops_the_constraint_and_no_rows(self, db):
        _production_shape(db)
        recorder = _upgrade(db)
        after_upgrade = db.query(PopulationData).count()

        _load_migration(recorder).downgrade()
        db.commit()

        assert recorder.constraints == []
        assert db.query(PopulationData).count() == after_upgrade


class TestTheWriterRefusesIt:
    """``services/auto_seeder.py`` is the writer whose fingerprint id=69 carries.

    Of population_data's five writers, only this one and ``bootstrap.py`` attach
    a row to the National Government ENTITY. bootstrap hardcodes year 2019 with a
    source document and confidence 0.95 (that is id=64); this one writes
    ``year = census_year or datetime.now().year`` with confidence 1.0, no source
    document and no metadata — which is id=69 exactly.
    """

    @pytest.fixture()
    def seeder_db(self, tmp_path, monkeypatch):
        engine = create_engine(f"sqlite:///{tmp_path/'seeder.db'}")
        Base.metadata.create_all(engine)
        Sess = sessionmaker(bind=engine)
        session = Sess()
        _country(session)
        _entity(session, "National Government", EntityType.NATIONAL)
        session.commit()

        # `services/__init__.py` does `from .auto_seeder import auto_seeder`,
        # which rebinds the package attribute `services.auto_seeder` to the
        # module-level SINGLETON. `import services.auto_seeder as m` then hands
        # back that AutoSeeder instance, not the module. Go through sys.modules.
        import services.auto_seeder  # noqa: F401  (ensure it is imported)

        auto_seeder_mod = sys.modules["services.auto_seeder"]
        monkeypatch.setattr(auto_seeder_mod, "SessionLocal", Sess)
        try:
            yield session, auto_seeder_mod
        finally:
            session.close()
            engine.dispose()

    @staticmethod
    def _run(module, session, payload):
        import asyncio

        class _Aggregator:
            async def fetch_all_population_data(self):
                return payload

        seeder = module.AutoSeeder()
        seeder.aggregator = _Aggregator()
        asyncio.run(seeder._seed_population_live())
        session.expire_all()

    def test_82_is_refused(self, seeder_db):
        """The exact payload that produced id=69.

        ``census_year`` absent means the writer stamps ``datetime.now().year``,
        which is why id=69's year equals the year it was created.
        """
        session, module = seeder_db

        self._run(
            module,
            session,
            {
                "fetch_success": True,
                "national_population": ID_69,
                "census_year": None,
                "counties": [],
                "source": "KNBS homepage scrape",
            },
        )

        assert session.query(PopulationData).count() == 0, (
            "the writer stored a national population of 82"
        )

    def test_a_refusal_does_not_overwrite_a_good_row(self, seeder_db):
        session, module = seeder_db
        national_id = (
            session.query(Entity).filter(Entity.type == EntityType.NATIONAL).one().id
        )
        from datetime import datetime

        this_year = datetime.now().year
        session.add(
            PopulationData(
                entity_id=national_id,
                year=this_year,
                total_population=NATIONAL_2019,
                source_document_id=1823,
            )
        )
        session.commit()

        self._run(
            module,
            session,
            {
                "fetch_success": True,
                "national_population": ID_69,
                "census_year": None,
                "counties": [],
            },
        )

        row = session.query(PopulationData).filter_by(entity_id=national_id).one()
        assert row.total_population == NATIONAL_2019

    def test_a_plausible_national_figure_still_lands(self, seeder_db):
        """The guard must not cost the well-formed case."""
        session, module = seeder_db

        self._run(
            module,
            session,
            {
                "fetch_success": True,
                "national_population": WORLD_BANK_2025,
                "census_year": 2025,
                "counties": [],
            },
        )

        row = session.query(PopulationData).one()
        assert (row.year, row.total_population) == (2025, WORLD_BANK_2025)


def test_the_floor_is_the_same_number_in_both_places(db):
    """A writer guard and a migration that disagree would be worse than either."""
    from services.auto_seeder import MIN_NATIONAL_POPULATION as writer_floor

    module = _load_migration(_RecordingOp(db.connection()))
    assert module.MIN_NATIONAL_POPULATION == writer_floor == 5_000_000
