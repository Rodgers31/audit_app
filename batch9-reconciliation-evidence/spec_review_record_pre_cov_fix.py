"""Write the independent Spec review with reproducible generator provenance."""
import hashlib
import json
import pathlib
import platform
import subprocess
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = pathlib.Path(__file__).with_name("spec-review.md")
BODY = """# Independent Spec review — #583 RECONCILIATION

Status: final Spec review — PASS for the scoped local operator tooling/procedure.
Production/operator/provider acceptance for #583 remains PENDING.
Earlier design and source findings below are retained as review history; their
final dispositions and executed controls appear in the final review section.
Reviewer owns no product files and performed no production operation.

Sources examined: issue #583 (OPEN), issues #581/#582 (OPEN), PR #584 head
`9e97ca3f1ca43f103a8655447a86d889456a218a` (matches the assignment),
`BATCH_8_EXCLUSION_CONTRACT.md`, `BATCH_8_NATIVE_EXCLUSION_HANDOFF.md`,
`batch8-exclusion-evidence/writer-inventory.md`, and source models/exclusion/worker.
Issue/PR reads: `gh issue view 583 --repo Rodgers31/audit_app --json title,body,state,comments,url`
and `gh pr view 584 --repo Rodgers31/audit_app --json title,body,headRefOid,headRefName,baseRefName,url`.

## Design requirements / prospective findings

1. **Trust boundary.** The proposed signed packet is compatible with the explicit
   operator evidence requirement only if its trusted target/scopes/keys policy is
   separately deployed and authenticated. An arbitrary policy supplied alongside
   an arbitrary signed packet would let the author self-authorize an unverified
   assertion. A signature authenticates an attestation; it cannot prove remote
   process death, stopped external work, or complete scheduler inventory.
   Receipt: contract lines 65–70 require ALL writers and external sessions stopped.

2. **Fencing and target identity.** NOLOGIN is insufficient on nonlogin group roles;
   inspect every login role's reachable effective writer privileges, direct owners,
   superusers, grants, memberships and prepared transactions. Re-check sessions
   and fencing in the committing transaction and document how concurrent reconnect,
   GRANT/role mutation, pooler visibility and incomplete pg_stat_activity visibility
   are excluded. Bind target to actual cluster/database identity, not a redacted URL.
   The operator path must fail closed when it cannot establish this boundary.

3. **Exact retained generation/effects.** Plan/apply snapshot must bind claim,
   entry/return evidence, command, dispatch row, worker generation and observations.
   Refuse any drift/new owner or a mismatched audits correlation. Preserve actual
   `returned_at`/`job_id`, and change only exact correlated RUNNING observations.
   Source: `backend/models.py:90–117`, `exclusion.py:219–259`, worker row-lock order.
   An aborted apply must leave all three durable components unchanged.

4. **All-writer packet.** Categories must cover native/manual invocation, worker,
   adapter/orphans, legacy ETL (#581), bootstrap (#582), application sessions,
   AutoSeeder, parliament, migrations and manual scripts. Repository inventory is
   incomplete proof of deployed host inventory: absent/uninspected categories or
   unknown process/session evidence must refuse. `writer-inventory.md` explicitly
   labels deployed hosts and URL equality UNVERIFIED.

No indispensable shared runtime-contract edit identified in the proposed design.
The dedicated dispatch activation/acquisition seam must remain unchanged.

## Refined maintenance design (source-only, execution pending)

The author replaced login-role exemptions with a whole-target maintenance outage:
an operator must independently set `pg_database.datallowconn=false`; the tool
retains its already-open direct connection, validates zero other target database
backends and zero prepared transactions, and holds the `pg_database` row `FOR SHARE`
through apply so admission cannot be reopened concurrently. It does not alter
admission or kill sessions. The read-only plan rolls back and is distinct from
the committing apply. This addresses the prospective credential-reconnect
loophole if implementation and independent executed controls prove those guards.
Include every target backend type, including background/logical writers.

A separate legacy exact-ID observation path can support the pre-migration census
only if independently audited and it never clears or absorbs an active/mismatched
claim, domain row, or command. Invalid/malformed claim-tag disposition must be
explicit; missing tag is not proof of a stopped writer.

Provenance note: this review supersedes its initial design-only rendering at the
same pinned target; the refinement changes the proposed design, not measured
runtime results. No executable acceptance result has been produced here.

## Operational limitation

Production RUNNING census, deployed pooler/direct idle cutoff, role/host inventory,
trusted policy deployment and real operator quiescence/effects approval are
unexecuted. Local controls can support the reviewed tooling/procedure gate for
#584, but cannot complete #583 or authorize migration/activation/release.
Actual workflow-state read: `gh api repos/Rodgers31/audit_app/actions/workflows`
returned `ci.yml`, `docker-build-deploy.yml`, `r2-acceptance.yml` and `seed.yml`
`disabled_manually`; this review performed no hosted execution.

## Initial implementation review (2026-10-09)

1. **P1 — native observation accepts foreign dispatch correlation.** Source
   `backend/seeding/reconciliation.py:265–268` checks dispatch tags only when
   a dispatch command exists. A native observation with the selected claim tag
   and foreign non-null dispatch tags is accepted as related. Requirement:
   “Refuse mismatched/new/active owners”; reject native observations bearing
   dispatch correlation. Reported to author for actual DB red/green regression.

2. **P1 — effects report is not bound to exact durable census.** The signed
   evidence schema (`reconciliation.py:118–119`) names target and selector, but
   no snapshot/generation hash. A freshly regenerated plan can therefore accept
   an effects report made before later same-claim durable changes. Apply's
   snapshot comparison (`:353–355`) protects plan→apply drift, not effects→plan
   drift. Requirement: “exact effects and observations reconciled” and refusal
   of durable-generation drift. Proposed repair: read-only census/preview first,
   have operator sign its exact snapshot hash, and enforce that equality in
   final plan/apply. Sent to author; executed regression pending.

These are source findings, not claims that exclusion was exercised. No final
Spec acceptance is issued until repaired controls and final diff are reviewed.

## Final independent Spec review (2026-10-09)

**Verdict: no unresolved Spec code finding in the inspected scoped delivery.**
The final product diff adds two operator modules, one additive migration after
e572b8c9a001, and changes only the corresponding model reconciliation CHECK.
No exclusion/worker/adapter/native CLI, ETL/bootstrap, dispatch defaults/mapping,
frontend/dependencies or workflow setting is modified.

Both earlier P1 findings are **valid and repaired**. Native correlated rows now
refuse any dispatch tags, including terminal rows; inspect→sign→plan→apply binds
the exact durable census and hashes all public-table effects. The preserved
`correlation-effects-red.json` records 4 failed/2 passed (including both original
findings); `repaired-core.json` records 80 passed, and final current/minimum
receipts record 102 passed each, zero skips. These selections overlap.

Source review confirms distinct read-only rollback inspection/planning, explicit
apply, same-backend admission-row/advisory/table locks through commit, exact
worker→domain→command→claim locking, repeated session/prepared/signature/time
checks, and atomic claim+dispatch+RUNNING+audit updates preserving original
entry/return/job evidence. Explicit-null and malformed legacy tags refuse;
preclaim truly untagged exact observations have an audited path.

`behavior/REPORT.md` and its two stable 91-check receipts cover real TCP admission
refusal, concurrent reopen blocking, operator SIGKILL/restart/backend death,
precommit rollback and postcommit report loss on minimum/current runtimes.
Parent process tests use real native `--all`, dedicated supervisor/adapter and
live orphan processes before/after effect commit, actual backend termination,
refusal followed by audited reconciliation and valid subsequent real runs.
`migrations-current.json` records 3 actual migration/history/RLS/grants/SQLite
checks; both final 102-check selections include them. No hosted execution is
claimed. The independent repaired-control rerun is recorded below.

`operator-procedure.md` correctly limits signatures to authenticated operator
attestation, requires exhaustive deployed host/scheduler/credential inventory,
holds real fences until explicit durable-audit verification, and separates local
direct PostgreSQL proof from provider/pooler feasibility and actual production
facts. `read_only_census.sql` explicitly BEGINs and verifies READ ONLY and rolls
back. The writer receipt's 397 source hashes, 15 registered domains, 1218 anchors
and generator hash were independently read back: zero source/generator drift.

This delivery can satisfy #584's missing reviewed operator implementation and
procedure code gate after coordinator acceptance. It cannot complete #583:
production census/effects reconciliation, provider/direct/pooler certification,
trusted policy deployment, complete real host/job evidence, authorized outage,
actual migration/activation and restoration remain real operator/coordinator
gates. No reduced-privilege or unlocked fallback is offered.
"""


def main():
    digest = hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    sources = [ROOT / "backend/seeding/reconciliation.py",
               ROOT / "backend/seeding/reconcile_operator.py", ROOT / "backend/models.py",
               ROOT / "backend/alembic/versions/e583b9c9a001_reconciliation_evidence.py"]
    sources += list(ROOT.glob("backend/tests/test_batch9_reconcil*.py"))
    sources += list(ROOT.glob("backend/tests/batch9_reconciliation_fixture/*.py"))
    hashes = "\n".join(f"Source `{p.relative_to(ROOT)}` SHA256: `{hashlib.sha256(p.read_bytes()).hexdigest()}`"
                       for p in sources if p.exists())
    preface = (f"Generated by: `batch9-reconciliation-evidence/spec_review_record.py`\n"
               f"Generator SHA256: `{digest}`\nTarget commit: `{head}`\n"
               f"Generated UTC: `{datetime.now(timezone.utc).isoformat()}`\n"
               f"Runtime: `{platform.python_version()}`\n{hashes}\n\n")
    verification = []
    if "--verify" in sys.argv:
        selections = [
            "backend/tests/test_batch9_reconciliation.py::test_native_claim_with_dispatch_tags_is_not_reconcilable",
            "backend/tests/test_batch9_reconciliation.py::test_plan_refuses_effects_committed_after_operator_effects_census",
            "backend/tests/test_batch9_reconciliation.py::test_dispatch_claim_command_domain_observations_and_audit_are_atomic",
            "backend/tests/test_batch9_reconciliation.py::test_dispatch_keeps_genuine_return_or_refusal_evidence",
            "backend/tests/test_batch9_reconciliation.py::test_new_owner_is_refused",
            "backend/tests/test_batch9_reconciliation.py::test_autocommit_backend_cannot_release",
            "backend/tests/test_batch9_reconciliation.py::test_preclaim_deployed_schema_legacy_observations_have_truthful_path",
            "backend/tests/test_batch9_reconciliation.py::test_audited_native_reconciliation_and_subsequent_native_run",
            "backend/tests/test_batch9_reconciliation.py::test_legacy_mode_never_treats_invalid_claim_tags_as_unclaimed",
            "backend/tests/test_batch9_reconciliation_migration.py",
        ]
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "PYTHONDONTWRITEBYTECODE": "1",
               "PYTHON_DOTENV_DISABLED": "1", "PYTHONPATH": str(ROOT / "backend"),
               "DATABASE_URL": "postgresql+psycopg2://postgres:batch9-inert-local@127.0.0.1:55493/batch9-reconciliation-a46a",
               "BATCH9_RECONCILIATION_DATABASE_URL": "postgresql+psycopg2://postgres:batch9-inert-local@127.0.0.1:55493/batch9-reconciliation-a46a"}
        before = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
        for runtime in ("/Users/roger/Documents/projects/audit_app/venv/bin/python", str(ROOT / ".batch9-min/bin/python")):
            command = [runtime, "-m", "pytest", *selections, "-q", "--no-cov", "-p", "no:cacheprovider"]
            version = subprocess.run([runtime, "-c", "import sys,sqlalchemy;print(sys.version);print('SQLAlchemy',sqlalchemy.__version__)"],
                                     cwd=ROOT, env=env, text=True, capture_output=True, check=True).stdout
            result = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
            verification.append({"command": command, "environment": env, "runtime": version,
                                 "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        after = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
        assert before == after, "Source drift during independent Spec controls"
        verification_text = "\n\n## Independent repaired-control execution\n\n```json\n" + json.dumps(verification, indent=2) + "\n```\n"
    else:
        verification_text = "\n\nIndependent rerun was not requested on this generator invocation.\n"
    OUT.write_text(preface + BODY + verification_text)
    check = OUT.read_text()
    assert digest in check and head in check and "final Spec review" in check
    if verification:
        assert all(v["exit_code"] == 0 for v in verification), "Independent control failure recorded"
        assert all(v["stdout"] in check for v in verification), "Execution receipt readback failed"
    print(f"Wrote {OUT.name}; generator={digest}; target={head}; provenance readback passed")


if __name__ == "__main__":
    main()
