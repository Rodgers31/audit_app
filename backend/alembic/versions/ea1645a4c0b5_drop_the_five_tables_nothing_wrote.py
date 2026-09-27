"""drop the five tables nothing ever wrote (#137 P6)

Revision ID: ea1645a4c0b5
Revises: 62a9f4131819
Create Date: 2026-09-26

DESTRUCTIVE. Requires the models-removal commit (``refactor(models): remove
the five models nothing ever wrote``) to be DEPLOYED first. ``ci.yml``'s
``run-migrations`` job applies this to production on push to ``main``. The
code before that commit queries ``pending_bills`` from two public endpoints,
and would return 500 against a dropped table until the backend is redeployed.

WHAT IS DROPPED, MEASURED
-------------------------
On a ``pg_dump`` clone of production taken 2026-09-26 22:27 UTC, stamped
``a2f7c1b48d90``:

    table               rows  inbound FKs  RLS  policies  views/triggers
    pending_bills          0            0   on         0               0
    fiscal_years           0            0   on         0               0
    county_org_units       0            0   on         0               0
    constituencies         0            0   on         0               0
    national_entities      0            0   on         0               0

No code in ``backend/``, ``etl/`` or ``scripts/`` constructs or inserts into
any of them (``tests/test_every_model_has_a_writer.py`` now enforces that for
every model). ``pending_bills`` also takes the enum type ``billtype``, which
no other column uses. ``figurebasis`` is shared with eleven other tables and
stays.

WHAT IS NOT DROPPED
-------------------
``parliament_source_documents`` is on the original P6 list. It holds 497 rows
and is written by ``etl/parliament_pipeline.py:405``, reached from
``main.py`` when ``PARLIAMENT_PIPELINE_ENABLED=1``. This migration names it
nowhere.

FAILS CLOSED
------------
The upgrade locks all present tables before counting and refuses (raising, so
the transaction rolls back and nothing is dropped) if any of the five holds one. A row appearing
there would mean a writer this analysis did not find. It would not mean the
data is disposable. It uses plain ``DROP TABLE`` with no ``CASCADE``, so an
inbound foreign key added later makes the drop fail rather than silently
taking the dependent constraint with it.

DOWNGRADE
---------
Recreates the five tables with the DDL production had, as dumped by
``pg_dump -s`` from the clone: columns, defaults, sequences, primary keys,
unique constraints, indexes, foreign keys and ROW LEVEL SECURITY. This is not
the DDL the baseline revision creates. Production had drifted from it (for
example, it lacks ``ix_constituencies_id`` and ``ix_fiscal_years_id``), and
production is what a rollback has to restore. Rows are not restored, because
there were none. GRANTs are not restated: on Supabase, the schema's default
privileges apply to a recreated table as they did to the original.
"""

from alembic import op
from sqlalchemy import text

revision = "ea1645a4c0b5"
# Rechained 2026-09-27 (was a2f7c1b48d90). #262's refile migration also
# revised a2f7c1b48d90, so merging both would have left two alembic heads and
# 'alembic upgrade head' (ci.yml run-migrations, the nightly migrate job)
# would refuse to run. One chain: a2f7c1b48d90 -> b8c4e2d17a90 (refile) ->
# 62a9f4131819 (#265 fixture rows) -> ea1645a4c0b5 (this).
down_revision = "62a9f4131819"
branch_labels = None
depends_on = None

#: None references another; locks are acquired in sorted name order.
TABLES = (
    "pending_bills",
    "fiscal_years",
    "county_org_units",
    "constituencies",
    "national_entities",
)

#: Enum types used only by the tables above.
ENUM_TYPES = ("billtype",)


def upgrade() -> None:
    bind = op.get_bind()

    present = sorted(
        t
        for t in TABLES
        if bind.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{t}"}).scalar()
        is not None
    )
    if present:
        bind.execute(text(
            "LOCK TABLE " + ", ".join(f"public.{table}" for table in present)
            + " IN ACCESS EXCLUSIVE MODE"
        ))
    holding = {}
    for table in present:
        n = bind.execute(text(f"SELECT count(*) FROM public.{table}")).scalar()
        if n:
            holding[table] = n
    if holding:
        raise RuntimeError(
            "ea1645a4c0b5 refuses to drop tables that hold rows: "
            + ", ".join(f"{t}={n}" for t, n in sorted(holding.items()))
            + ". Something wrote them that #137 P6 did not find; establish "
            "what before dropping anything."
        )

    for table in present:
        op.execute(f"DROP TABLE public.{table}")
    for enum_type in ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS public.{enum_type}")


def downgrade() -> None:
    for statement in _PRODUCTION_DDL:
        op.execute(statement)


# pg_dump -s --no-owner --no-privileges of the five tables on the 2026-09-26
# production clone, one statement per entry, in pg_dump's dependency order.
_PRODUCTION_DDL = (
    "CREATE TYPE public.billtype AS ENUM "
    "('SUPPLIER_ARREARS', 'SALARY', 'PENSION', 'STATUTORY', 'COURT_AWARDS', 'OTHER')",
    """CREATE TABLE public.constituencies (
    id integer NOT NULL,
    name character varying(200) NOT NULL,
    code character varying(20),
    county_entity_id integer NOT NULL,
    population integer,
    registered_voters integer,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT now()
)""",
    "CREATE SEQUENCE public.constituencies_id_seq AS integer START WITH 1 "
    "INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.constituencies_id_seq OWNED BY public.constituencies.id",
    """CREATE TABLE public.county_org_units (
    id integer NOT NULL,
    entity_id integer NOT NULL,
    name character varying(200) NOT NULL,
    unit_type character varying(50) DEFAULT 'sub_county'::character varying NOT NULL,
    code character varying(20),
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT now()
)""",
    "CREATE SEQUENCE public.county_org_units_id_seq AS integer START WITH 1 "
    "INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.county_org_units_id_seq OWNED BY public.county_org_units.id",
    """CREATE TABLE public.fiscal_years (
    id integer NOT NULL,
    label character varying(20) NOT NULL,
    start_date timestamp without time zone NOT NULL,
    end_date timestamp without time zone NOT NULL,
    is_current boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT now()
)""",
    "CREATE SEQUENCE public.fiscal_years_id_seq AS integer START WITH 1 "
    "INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.fiscal_years_id_seq OWNED BY public.fiscal_years.id",
    """CREATE TABLE public.national_entities (
    id integer NOT NULL,
    entity_id integer NOT NULL,
    parent_ministry_entity_id integer,
    establishment_act character varying(300),
    website character varying(300),
    category character varying(50),
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT now()
)""",
    "CREATE SEQUENCE public.national_entities_id_seq AS integer START WITH 1 "
    "INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.national_entities_id_seq OWNED BY public.national_entities.id",
    """CREATE TABLE public.pending_bills (
    id integer NOT NULL,
    entity_id integer NOT NULL,
    bill_type public.billtype NOT NULL,
    amount numeric(15,2) NOT NULL,
    fiscal_year character varying(20) NOT NULL,
    aging_days integer,
    eligible_amount numeric(15,2),
    ineligible_amount numeric(15,2),
    source_document_id integer,
    metadata jsonb,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    extraction_id integer,
    page_ref character varying(50),
    source_hash character varying(64),
    confidence_score double precision,
    basis public.figurebasis,
    publishable boolean DEFAULT false NOT NULL,
    quarantine_reason character varying(120)
)""",
    "CREATE SEQUENCE public.pending_bills_id_seq AS integer START WITH 1 "
    "INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
    "ALTER SEQUENCE public.pending_bills_id_seq OWNED BY public.pending_bills.id",
    "ALTER TABLE ONLY public.constituencies ALTER COLUMN id SET DEFAULT "
    "nextval('public.constituencies_id_seq'::regclass)",
    "ALTER TABLE ONLY public.county_org_units ALTER COLUMN id SET DEFAULT "
    "nextval('public.county_org_units_id_seq'::regclass)",
    "ALTER TABLE ONLY public.fiscal_years ALTER COLUMN id SET DEFAULT "
    "nextval('public.fiscal_years_id_seq'::regclass)",
    "ALTER TABLE ONLY public.national_entities ALTER COLUMN id SET DEFAULT "
    "nextval('public.national_entities_id_seq'::regclass)",
    "ALTER TABLE ONLY public.pending_bills ALTER COLUMN id SET DEFAULT "
    "nextval('public.pending_bills_id_seq'::regclass)",
    "ALTER TABLE ONLY public.constituencies ADD CONSTRAINT constituencies_pkey PRIMARY KEY (id)",
    "ALTER TABLE ONLY public.county_org_units ADD CONSTRAINT county_org_units_pkey PRIMARY KEY (id)",
    "ALTER TABLE ONLY public.fiscal_years ADD CONSTRAINT fiscal_years_pkey PRIMARY KEY (id)",
    "ALTER TABLE ONLY public.national_entities ADD CONSTRAINT national_entities_pkey PRIMARY KEY (id)",
    "ALTER TABLE ONLY public.pending_bills ADD CONSTRAINT pending_bills_pkey PRIMARY KEY (id)",
    "ALTER TABLE ONLY public.constituencies ADD CONSTRAINT uq_constituency_name UNIQUE (name)",
    "ALTER TABLE ONLY public.county_org_units "
    "ADD CONSTRAINT uq_county_org_entity_name UNIQUE (entity_id, name)",
    "ALTER TABLE ONLY public.national_entities ADD CONSTRAINT uq_national_entity UNIQUE (entity_id)",
    "ALTER TABLE ONLY public.pending_bills "
    "ADD CONSTRAINT uq_pending_bill_entity_type_fy UNIQUE (entity_id, bill_type, fiscal_year)",
    "CREATE UNIQUE INDEX ix_constituencies_code ON public.constituencies USING btree (code)",
    "CREATE INDEX ix_constituencies_county_entity_id ON public.constituencies "
    "USING btree (county_entity_id)",
    "CREATE INDEX ix_county_org_units_entity_id ON public.county_org_units USING btree (entity_id)",
    "CREATE UNIQUE INDEX ix_fiscal_years_label ON public.fiscal_years USING btree (label)",
    "CREATE INDEX ix_national_entities_parent_ministry_entity_id ON public.national_entities "
    "USING btree (parent_ministry_entity_id)",
    "CREATE INDEX ix_pending_bills_basis ON public.pending_bills USING btree (basis)",
    "CREATE INDEX ix_pending_bills_extraction_id ON public.pending_bills USING btree (extraction_id)",
    "CREATE INDEX ix_pending_bills_fiscal_year ON public.pending_bills USING btree (fiscal_year)",
    "CREATE INDEX ix_pending_bills_id ON public.pending_bills USING btree (id)",
    "CREATE INDEX ix_pending_bills_publishable ON public.pending_bills USING btree (publishable)",
    "CREATE INDEX ix_pending_bills_source_document_id ON public.pending_bills "
    "USING btree (source_document_id)",
    "ALTER TABLE ONLY public.constituencies ADD CONSTRAINT constituencies_county_entity_id_fkey "
    "FOREIGN KEY (county_entity_id) REFERENCES public.entities(id)",
    "ALTER TABLE ONLY public.county_org_units ADD CONSTRAINT county_org_units_entity_id_fkey "
    "FOREIGN KEY (entity_id) REFERENCES public.entities(id)",
    "ALTER TABLE ONLY public.pending_bills ADD CONSTRAINT fk_pending_bills_extraction_id_extractions "
    "FOREIGN KEY (extraction_id) REFERENCES public.extractions(id)",
    "ALTER TABLE ONLY public.national_entities ADD CONSTRAINT national_entities_entity_id_fkey "
    "FOREIGN KEY (entity_id) REFERENCES public.entities(id)",
    "ALTER TABLE ONLY public.national_entities "
    "ADD CONSTRAINT national_entities_parent_ministry_entity_id_fkey "
    "FOREIGN KEY (parent_ministry_entity_id) REFERENCES public.entities(id)",
    "ALTER TABLE ONLY public.pending_bills ADD CONSTRAINT pending_bills_entity_id_fkey "
    "FOREIGN KEY (entity_id) REFERENCES public.entities(id)",
    "ALTER TABLE ONLY public.pending_bills ADD CONSTRAINT pending_bills_source_document_id_fkey "
    "FOREIGN KEY (source_document_id) REFERENCES public.source_documents(id)",
    "ALTER TABLE public.constituencies ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE public.county_org_units ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE public.fiscal_years ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE public.national_entities ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE public.pending_bills ENABLE ROW LEVEL SECURITY",
)
