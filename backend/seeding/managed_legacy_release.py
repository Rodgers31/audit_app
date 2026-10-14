"""Compile a reviewed, atomic legacy-job repair for managed PostgreSQL.

This is an operator tool, never runtime expiry or claim reclamation. Database
locks protect public row effects; independently held host, DDL and external
effect fences remain necessary. The strict retained-superuser operator is
unchanged. Execute the complete SQL block, then inspect committed audit/jobs
through a new read-only transaction. Never retry an ambiguous response.
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

from services.admin_audit_storage import CAPTURE_BODY, IMMUTABLE_BODY

MAX_BYTES = 262144
FENCES = ("render", "github", "manual", "ddl", "external", "provider_queue")
TAGS = (
    "seeding_claim_id",
    "dispatch_command_id",
    "dispatch_claim_token",
    "operator_reconciliation",
)


class ReleaseRefused(ValueError):
    pass


def canonical(value):
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, RecursionError):
        raise ReleaseRefused("invalid_json") from None
    if len(raw.encode()) > MAX_BYTES:
        raise ReleaseRefused("input_bound")
    return raw


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def require(value, reason):
    if value is not True:
        raise ReleaseRefused(reason)


def exact(value, keys):
    require(type(value) is dict and set(value) == set(keys.split()), "shape")


def label(value, limit=500):
    return (
        type(value) is str
        and 0 < len(value) <= limit
        and value == value.strip()
        and not any(ord(c) < 32 for c in value)
    )


def hash_value(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def utc(value):
    require(type(value) is str, "timestamp")
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        raise ReleaseRefused("timestamp") from None
    require(result.utcoffset() == timedelta(0), "timestamp")
    return result


def literal(value):
    # Standard-conforming SQL strings; backslashes are literal, quotes doubled.
    require(type(value) is str and "\x00" not in value, "sql_literal")
    return "'" + value.replace("'", "''") + "'"


CATALOG_SQL = """SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY name,kind),'[]'::jsonb) FROM (
 SELECT c.relname AS name,c.relkind::text AS kind,pg_get_userbyid(c.relowner) AS owner,
 c.relrowsecurity AS rls,c.relforcerowsecurity AS force_rls,
 coalesce(c.relacl::text,'') AS acl,
 coalesce((SELECT jsonb_agg(jsonb_build_object('name',a.attname,'type',format_type(a.atttypid,a.atttypmod),
 'not_null',a.attnotnull,'identity',a.attidentity,'generated',a.attgenerated,'default',pg_get_expr(d.adbin,d.adrelid)) ORDER BY a.attnum)
 FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
 WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped),'[]'::jsonb) AS columns,
 coalesce((SELECT jsonb_agg(pg_get_constraintdef(k.oid,true) ORDER BY k.conname)
 FROM pg_constraint k WHERE k.conrelid=c.oid),'[]'::jsonb) AS constraints,
 coalesce((SELECT jsonb_agg(jsonb_build_object('name',k.conname,'type',k.contype,
 'validated',k.convalidated,'definition',pg_get_constraintdef(k.oid,true),
 'ready',CASE WHEN k.conindid=0 THEN true ELSE i.indisvalid AND i.indisready AND i.indisunique END) ORDER BY k.conname)
 FROM pg_constraint k LEFT JOIN pg_index i ON i.indexrelid=k.conindid WHERE k.conrelid=c.oid),'[]'::jsonb) AS constraint_details,
 coalesce((SELECT jsonb_agg(jsonb_build_object('name',t.tgname,'enabled',t.tgenabled,
 'definition',pg_get_triggerdef(t.oid,true),'function',pg_get_functiondef(t.tgfoid),
 'body',btrim(f.prosrc),'security_definer',f.prosecdef,'config',f.proconfig,
 'owned',f.proowner=c.relowner,'type',t.tgtype,'unconditional',t.tgqual IS NULL,'no_args',t.tgnargs=0) ORDER BY t.tgname)
 FROM pg_trigger t JOIN pg_proc f ON f.oid=t.tgfoid
 WHERE t.tgrelid=c.oid AND NOT t.tgisinternal),'[]'::jsonb) AS triggers
 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relkind IN ('r','p','f','m','v')
) x"""


def validate(policy, now=None):
    canonical(policy)
    exact(
        policy,
        "version target catalog jobs effects who why effect_review fences observed_at hold_until",
    )
    require(type(policy["version"]) is int and policy["version"] == 2, "version")
    target = policy["target"]
    exact(target, "database database_oid system_identifier maintenance_role revision")
    require(
        all(
            label(target[k], 100) for k in ("database", "maintenance_role", "revision")
        ),
        "target",
    )
    require(target["revision"] == "a611b12a0001", "audit_revision")
    require(
        type(target["database_oid"]) is int and 0 < target["database_oid"] < 2**32,
        "target",
    )
    require(
        type(target["system_identifier"]) is str
        and target["system_identifier"].isascii()
        and target["system_identifier"].isdigit()
        and 0 < int(target["system_identifier"]) < 2**64,
        "target",
    )
    require(
        label(policy["who"], 64)
        and label(policy["why"])
        and label(policy["effect_review"], 1500),
        "review",
    )
    observed, hold = utc(policy["observed_at"]), utc(policy["hold_until"])
    now = now or datetime.now(timezone.utc)
    require(
        now - timedelta(minutes=5)
        <= observed
        <= now
        < hold
        <= observed + timedelta(minutes=5),
        "expired",
    )
    exact(policy["fences"], " ".join(FENCES))
    for fence in policy["fences"].values():
        exact(fence, "state artifact_sha256 description")
        require(
            fence["state"] in ("stopped", "absent")
            and hash_value(fence["artifact_sha256"])
            and label(fence["description"], 1000),
            "fence",
        )
    jobs, effects, catalog = policy["jobs"], policy["effects"], policy["catalog"]
    require(type(jobs) is list and 1 <= len(jobs) <= 10, "jobs")
    require(type(effects) is dict and 2 <= len(effects) <= 200, "effects")
    require(type(catalog) is list and 2 <= len(catalog) <= 300, "catalog")
    ids = []
    for job in jobs:
        require(
            type(job) is dict
            and type(job.get("id")) is int
            and 0 < job["id"] < 2**31,
            "job",
        )
        require(
            label(job.get("domain"), 100)
            and job.get("status") == "RUNNING"
            and job.get("finished_at") is None
            and type(job.get("dry_run")) is bool,
            "job",
        )
        require(
            type(job.get("metadata")) is dict
            and not set(TAGS).intersection(job["metadata"])
            and type(job.get("errors")) is list,
            "legacy_job",
        )
        ids.append(job["id"])
    require(ids == sorted(set(ids)), "job_ids")
    names = []
    for row in catalog:
        require(
            type(row) is dict
            and label(row.get("name"), 63)
            and row.get("kind") in ("r", "p", "v"),
            "catalog",
        )
        if row["kind"] in ("r", "p"):
            require(row.get("owner") == target["maintenance_role"], "table_owner")
            names.append(row["name"])
    require(
        sorted(names) == sorted(effects)
        and {
            "ingestion_jobs",
            "admin_audit_log",
            "alembic_version",
            "admin_audit_provenance",
            "admin_audit_storage",
        }
        <= set(names),
        "table_inventory",
    )
    # Run after the accepted capture migration, while storage is uncertified.
    # Only its exact capture/append-only triggers are admitted.
    expected_triggers = {
        "ingestion_jobs": {},
        "admin_audit_log": {
            "audit_log_capture": (5, CAPTURE_BODY, True),
            "audit_log_immutable": (58, IMMUTABLE_BODY, False),
        },
        "admin_audit_provenance": {
            "audit_provenance_immutable": (58, IMMUTABLE_BODY, False)
        },
        "admin_audit_storage": {},
    }
    sidecar_columns = {
        "admin_audit_provenance": [
            ("audit_id", "integer"),
            ("root_xid", "xid8"),
            ("incarnation", "uuid"),
        ],
        "admin_audit_storage": [
            ("singleton", "boolean"),
            ("schema_version", "integer"),
            ("incarnation", "uuid"),
            ("system_identifier", "text"),
            ("database_oid", "oid"),
            ("timeline", "integer"),
            ("certified", "boolean"),
        ],
    }
    sidecar_constraints = {
        "admin_audit_log": {
            "admin_audit_log_pkey": ("p", "PRIMARY KEY (id)"),
            "ck_admin_audit_positive_id": ("c", "CHECK (id > 0)"),
        },
        "admin_audit_provenance": {
            "admin_audit_provenance_pkey": ("p", "PRIMARY KEY (audit_id)"),
            "admin_audit_provenance_audit_id_fkey": (
                "f",
                "FOREIGN KEY (audit_id) REFERENCES admin_audit_log(id)",
            ),
        },
        "admin_audit_storage": {
            "admin_audit_storage_pkey": ("p", "PRIMARY KEY (singleton)"),
            "ck_audit_storage_singleton": ("c", "CHECK (singleton)"),
            "ck_audit_storage_version": ("c", "CHECK (schema_version = 1)"),
        },
    }
    for row in catalog:
        if row["name"] in sidecar_columns:
            columns = row.get("columns")
            require(
                type(columns) is list
                and [(c.get("name"), c.get("type")) for c in columns]
                == sidecar_columns[row["name"]]
                and all(
                    c.get("not_null") is True
                    and c.get("identity") == ""
                    and c.get("generated") == ""
                    and (
                        c.get("default") is None
                        or (c["name"] == "certified" and c["default"] == "false")
                    )
                    for c in columns
                ),
                "audit_sidecar_columns",
            )
        if row["name"] in sidecar_constraints:
            details = row.get("constraint_details")
            expected = sidecar_constraints[row["name"]]
            require(
                type(details) is list
                and len(details) == len(expected)
                and {d.get("name") for d in details} == set(expected),
                "audit_sidecar_constraints",
            )
            for detail in details:
                require(
                    (detail.get("type"), detail.get("definition"))
                    == expected[detail["name"]]
                    and detail.get("validated") is True
                    and detail.get("ready") is True,
                    "audit_sidecar_constraints",
                )
        if row["name"] in expected_triggers:
            expected = expected_triggers[row["name"]]
            triggers = row.get("triggers")
            require(
                type(triggers) is list and len(triggers) == len(expected),
                "mutation_trigger",
            )
            require(
                {t.get("name") for t in triggers} == set(expected), "mutation_trigger"
            )
            for t in triggers:
                require(
                    (t.get("type"), t.get("body"), t.get("security_definer"))
                    == expected[t["name"]]
                    and t.get("enabled") == "A"
                    and t.get("config") == ["search_path=pg_catalog"]
                    and t.get("owned") is True
                    and t.get("unconditional") is True
                    and t.get("no_args") is True,
                    "mutation_trigger",
                )
        if row["name"] == "admin_audit_log":
            columns = row.get("columns")
            require(type(columns) is list, "audit_columns")
            require(
                {c.get("name") for c in columns}
                == {
                    "id",
                    "actor_id",
                    "actor_email",
                    "action",
                    "target_type",
                    "target_id",
                    "payload",
                    "created_at",
                },
                "audit_columns",
            )
            id_column = next(c for c in columns if c["name"] == "id")
            require(
                type(id_column.get("default")) is str
                and re.fullmatch(
                    r"nextval\('(?:public\.)?admin_audit_log_id_seq'::regclass\)",
                    id_column["default"],
                )
                is not None,
                "audit_identity_default",
            )
            require(
                all(
                    c.get("generated") == ""
                    and c.get("identity") == ""
                    and (
                        c["name"] in ("id", "created_at")
                        or c.get("default") is None
                        or (c["name"] == "payload" and c["default"] == "'{}'::jsonb")
                    )
                    for c in columns
                ),
                "audit_defaults",
            )
    for name, value in effects.items():
        exact(value, "rows sha256")
        require(
            type(value["rows"]) is int
            and 0 <= value["rows"] <= 100000
            and hash_value(value["sha256"]),
            "effects",
        )
    return policy


def compile_sql(policy):
    """No database access; trusted file fingerprint is checked at this boundary."""
    expected = os.environ.get("AUDIT_MANAGED_RELEASE_POLICY_SHA256")
    require(
        hash_value(expected) and expected == digest(policy),
        "trusted_policy_fingerprint",
    )
    validate(policy)
    operation = digest(policy)
    source = sha256(Path(__file__).read_bytes()).hexdigest()
    payload = {
        "version": 2,
        "operation_sha256": operation,
        "generator_sha256": source,
        "who": policy["who"],
        "why": policy["why"],
        "effects": policy["effect_review"],
        "outcome": "execution_unverified",
        "job_ids": [j["id"] for j in policy["jobs"]],
        "target": policy["target"],
        "fences": policy["fences"],
    }
    require(len(canonical(payload)) <= 12000, "audit_bound")
    domains = sorted({j["domain"] for j in policy["jobs"]})
    keys = [
        int.from_bytes(sha256(("seeding:" + d).encode()).digest()[:8], "big")
        & (2**63 - 1)
        for d in domains
    ]
    values = {
        "POLICY": literal(canonical(policy)),
        "PAYLOAD": literal(canonical(payload)),
        "CATALOG": CATALOG_SQL,
        "KEYS": ",".join(str(k) for k in keys),
    }
    # The DO body contains reviewed strings. Its delimiter must not occur in
    # any inserted input, including catalog function definitions.
    tag = "$managed_release_" + operation[:16] + "$"
    while any(tag in value for value in values.values()):
        tag = tag[:-1] + "_x$"
    template = TEMPLATE.replace("$managed_release$", tag)
    # One pass: marker-like text inside reviewed descriptions is data, never a
    # second template substitution that could escape its original SQL literal.
    return re.sub(
        r"__(POLICY|PAYLOAD|CATALOG|KEYS)__", lambda m: values[m[1]], template
    )


TEMPLATE = """-- Managed legacy reconciliation: execute the entire guarded block.
BEGIN;
SET LOCAL search_path=pg_catalog,public;
SET LOCAL TimeZone='UTC';
SET LOCAL standard_conforming_strings=on;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='30s';
SET LOCAL idle_in_transaction_session_timeout='30s';
DO $managed_release$
<<managed_repair>>
DECLARE
 p jsonb := __POLICY__::jsonb;
 record jsonb := __PAYLOAD__::jsonb;
 actual jsonb; original jsonb; original_provenance jsonb; expected jsonb; before_other jsonb; after_other jsonb;
 table_name text; job jsonb; audit_id integer;
 tables text[]; domain_key bigint; n bigint; h text; at_time timestamp;
BEGIN
 IF clock_timestamp() < (p->>'observed_at')::timestamptz OR
 clock_timestamp() >= (p->>'hold_until')::timestamptz THEN RAISE EXCEPTION 'managed_release:expired'; END IF;
 SELECT jsonb_build_object('database',current_database(),'database_oid',d.oid::bigint,
 'system_identifier',s.system_identifier::text,'maintenance_role',current_user,
 'revision',(SELECT version_num FROM public.alembic_version)) INTO actual
 FROM pg_database d CROSS JOIN pg_control_system() s WHERE d.datname=current_database();
 IF actual IS DISTINCT FROM p->'target' THEN RAISE EXCEPTION 'managed_release:target'; END IF;
 IF (SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user) IS NOT TRUE THEN RAISE EXCEPTION 'managed_release:visibility'; END IF;
 IF EXISTS(SELECT FROM pg_prepared_xacts WHERE database=current_database()) THEN RAISE EXCEPTION 'managed_release:prepared'; END IF;
 IF EXISTS(SELECT FROM pg_rewrite w JOIN pg_class c ON c.oid=w.ev_class JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='public' AND c.relname IN ('ingestion_jobs','admin_audit_log','admin_audit_provenance','admin_audit_storage') AND w.rulename<>'_RETURN') THEN RAISE EXCEPTION 'managed_release:rule'; END IF;
 SELECT array_agg(tablename ORDER BY tablename) INTO tables FROM pg_tables WHERE schemaname='public';
 IF tables IS NULL OR cardinality(tables)<3 THEN RAISE EXCEPTION 'managed_release:inventory'; END IF;
 FOREACH domain_key IN ARRAY ARRAY[__KEYS__]::bigint[] LOOP
  IF pg_try_advisory_xact_lock(domain_key) IS NOT TRUE THEN RAISE EXCEPTION 'managed_release:domain_busy'; END IF;
 END LOOP;
 FOREACH table_name IN ARRAY tables LOOP
  EXECUTE format('LOCK TABLE public.%I IN SHARE ROW EXCLUSIVE MODE NOWAIT',table_name);
 END LOOP;
 SELECT (__CATALOG__) INTO actual;
 IF actual IS DISTINCT FROM p->'catalog' THEN RAISE EXCEPTION 'managed_release:catalog'; END IF;
 FOREACH table_name IN ARRAY tables LOOP
  EXECUTE format($census$SELECT count(*),encode(sha256(convert_to(coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') FROM (SELECT encode(sha256(convert_to(to_jsonb(r)::text,'UTF8')),'hex') h FROM public.%I r LIMIT 100001) x$census$,table_name) INTO n,h;
  IF jsonb_build_object('rows',n,'sha256',h) IS DISTINCT FROM p->'effects'->table_name THEN RAISE EXCEPTION 'managed_release:effects'; END IF;
 END LOOP;
 SELECT coalesce(jsonb_agg(to_jsonb(j) ORDER BY id),'[]'::jsonb) INTO actual FROM public.ingestion_jobs j WHERE status='RUNNING';
 IF actual IS DISTINCT FROM p->'jobs' THEN RAISE EXCEPTION 'managed_release:jobs'; END IF;
 IF (SELECT count(*) FROM public.admin_audit_storage)<>1 OR NOT EXISTS(
 SELECT FROM public.admin_audit_storage s CROSS JOIN pg_control_checkpoint() c
 WHERE s.singleton AND s.schema_version=1 AND s.certified IS FALSE AND s.incarnation IS NOT NULL
 AND s.system_identifier=p->'target'->>'system_identifier'
 AND s.database_oid=(p->'target'->>'database_oid')::oid AND s.timeline=c.timeline_id)
 THEN RAISE EXCEPTION 'managed_release:audit_epoch'; END IF;
 IF EXISTS(SELECT FROM public.admin_audit_log a LEFT JOIN public.admin_audit_provenance v ON v.audit_id=a.id
 WHERE v.audit_id IS NULL OR v.incarnation IS NULL OR v.root_xid IS NULL
 OR v.incarnation<>(SELECT incarnation FROM public.admin_audit_storage)
 OR v.root_xid<'3'::xid8 OR v.root_xid>=pg_snapshot_xmax(pg_current_snapshot()))
 THEN RAISE EXCEPTION 'managed_release:unknown_audit_history'; END IF;
 IF EXISTS(SELECT FROM public.admin_audit_provenance v LEFT JOIN public.admin_audit_log a ON a.id=v.audit_id WHERE a.id IS NULL)
 OR EXISTS(SELECT FROM public.admin_audit_provenance v GROUP BY v.audit_id HAVING count(*)<>1)
 THEN RAISE EXCEPTION 'managed_release:invalid_audit_history'; END IF;
 IF to_regclass('public.seeding_domain_claims') IS NOT NULL THEN
  EXECUTE 'SELECT count(*) FROM public.seeding_domain_claims WHERE released_at IS NULL' INTO n;
  IF n<>0 THEN RAISE EXCEPTION 'managed_release:retained_claim'; END IF;
 END IF;
 IF to_regclass('public.etl_dispatch_worker') IS NOT NULL THEN
  EXECUTE 'SELECT count(*) FROM public.etl_dispatch_worker WHERE ready' INTO n;
  IF n<>0 THEN RAISE EXCEPTION 'managed_release:worker'; END IF;
 END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(j) ORDER BY id),'[]'::jsonb) INTO before_other FROM public.ingestion_jobs j WHERE id NOT IN (SELECT (value->>'id')::integer FROM jsonb_array_elements(p->'jobs'));
 SELECT coalesce(jsonb_agg(to_jsonb(a) ORDER BY id),'[]'::jsonb) INTO original FROM public.admin_audit_log a;
 SELECT coalesce(jsonb_agg(to_jsonb(v) ORDER BY v.audit_id),'[]'::jsonb) INTO original_provenance FROM public.admin_audit_provenance v;
 IF clock_timestamp()>=(p->>'hold_until')::timestamptz THEN RAISE EXCEPTION 'managed_release:expired'; END IF;
 at_time := clock_timestamp() AT TIME ZONE 'UTC';
 INSERT INTO public.admin_audit_log(actor_id,action,target_type,target_id,payload,created_at)
 VALUES(p->>'who','seeding.reconcile.managed','legacy_ingestion',NULL,record,at_time) RETURNING id INTO audit_id;
 IF audit_id IS NULL OR audit_id<1 THEN RAISE EXCEPTION 'managed_release:audit'; END IF;
 FOR job IN SELECT value FROM jsonb_array_elements(p->'jobs') LOOP
  expected := job || jsonb_build_object('status','FAILED','finished_at',at_time,
   'errors',(job->'errors') || jsonb_build_array('Operator reconciliation audit '||audit_id||': execution remains unverified'),
   'metadata',(job->'metadata')||jsonb_build_object('operator_reconciliation',jsonb_build_object('audit_id',audit_id,'operation_sha256',record->>'operation_sha256','who',p->>'who')));
  UPDATE public.ingestion_jobs SET status='FAILED',finished_at=at_time,errors=expected->'errors',metadata=expected->'metadata'
  WHERE id=(job->>'id')::integer AND status='RUNNING';
  IF NOT FOUND THEN RAISE EXCEPTION 'managed_release:job_write'; END IF;
  SELECT to_jsonb(j) INTO actual FROM public.ingestion_jobs j WHERE id=(job->>'id')::integer;
  IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'managed_release:job_readback'; END IF;
 END LOOP;
 SET CONSTRAINTS ALL IMMEDIATE;
 SELECT coalesce(jsonb_agg(to_jsonb(j) ORDER BY id),'[]'::jsonb) INTO after_other FROM public.ingestion_jobs j WHERE id NOT IN (SELECT (value->>'id')::integer FROM jsonb_array_elements(p->'jobs'));
 IF after_other IS DISTINCT FROM before_other THEN RAISE EXCEPTION 'managed_release:other_jobs'; END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(a) ORDER BY id),'[]'::jsonb) INTO actual FROM public.admin_audit_log a WHERE id<>audit_id;
 IF actual IS DISTINCT FROM original THEN RAISE EXCEPTION 'managed_release:prior_audit'; END IF;
 SELECT to_jsonb(a) INTO actual FROM public.admin_audit_log a WHERE id=audit_id;
 IF actual IS DISTINCT FROM jsonb_build_object('id',audit_id,'actor_id',p->>'who','actor_email',NULL,'action','seeding.reconcile.managed','target_type','legacy_ingestion','target_id',NULL,'payload',record,'created_at',at_time) THEN RAISE EXCEPTION 'managed_release:audit_readback'; END IF;
 SELECT to_jsonb(v) INTO actual FROM public.admin_audit_provenance v WHERE v.audit_id=managed_repair.audit_id;
 IF actual IS DISTINCT FROM jsonb_build_object('audit_id',audit_id,'root_xid',pg_current_xact_id(),
 'incarnation',(SELECT incarnation FROM public.admin_audit_storage)) THEN RAISE EXCEPTION 'managed_release:capture'; END IF;
 SELECT coalesce(jsonb_agg(to_jsonb(v) ORDER BY v.audit_id),'[]'::jsonb) INTO actual FROM public.admin_audit_provenance v WHERE v.audit_id<>managed_repair.audit_id;
 IF actual IS DISTINCT FROM original_provenance THEN RAISE EXCEPTION 'managed_release:prior_provenance'; END IF;
 FOREACH table_name IN ARRAY tables LOOP
  IF table_name IN ('ingestion_jobs','admin_audit_log','admin_audit_provenance') THEN CONTINUE; END IF;
  EXECUTE format($census$SELECT count(*),encode(sha256(convert_to(coalesce(string_agg(h,'' ORDER BY h),''),'UTF8')),'hex') FROM (SELECT encode(sha256(convert_to(to_jsonb(r)::text,'UTF8')),'hex') h FROM public.%I r LIMIT 100001) x$census$,table_name) INTO n,h;
  IF jsonb_build_object('rows',n,'sha256',h) IS DISTINCT FROM p->'effects'->table_name THEN RAISE EXCEPTION 'managed_release:side_effect'; END IF;
 END LOOP;
 SELECT (__CATALOG__) INTO actual;
 IF actual IS DISTINCT FROM p->'catalog' OR clock_timestamp()>=(p->>'hold_until')::timestamptz THEN RAISE EXCEPTION 'managed_release:final_guard'; END IF;
END
$managed_release$;
COMMIT;
-- A separate fresh read-only query must verify committed audit/job state.
"""
