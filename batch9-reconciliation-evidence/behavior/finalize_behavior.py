"""Read back independent verification receipts and write an attributed final memo."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

ROOT=Path(__file__).resolve().parents[2]
DIRECTORY=Path(__file__).parent

def main():
    loaded={p.stem:json.loads(p.read_text()) for p in DIRECTORY.glob('*.json')}
    failures=[]
    for name,receipt in loaded.items():
        generator=ROOT/receipt['generated_by']
        if hashlib.sha256(generator.read_bytes()).hexdigest()!=receipt['generator_sha256']:
            failures.append(name+': generator changed')
    assert not failures,failures
    latest=[loaded[n] for n in ('min-final','current-final')]
    assert all(r['verdict']=='PASSED' and len(r['checks'])==91 and not r['source_changed_during_run'] for r in latest)
    assert latest[0]['source_sha256_after']==latest[1]['source_sha256_after']
    sources=latest[0]['source_sha256_after']
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==v for p,v in sources.items()),'Source changed after final verification'
    engine=create_engine('postgresql+psycopg2://postgres:batch9-inert-local@127.0.0.1:55493/postgres',poolclass=NullPool,isolation_level='AUTOCOMMIT')
    with engine.connect() as connection:
        remaining=connection.execute(text("SELECT datname,datallowconn FROM pg_database WHERE datname LIKE 'batch9-reconciliation-behavior-%' ORDER BY datname")).mappings().all()
    engine.dispose()
    assert not remaining,remaining
    removed=[]
    for path in DIRECTORY.iterdir():
        if path.is_dir() and (path.name.startswith('policy-controls-') or path.name.startswith('batch9-reconciliation-behavior-') and path.name.endswith('-io')):
            removed.append(path.name);shutil.rmtree(path)
    message='''Independent behavior verification completed on owned loopback PostgreSQL fixtures only.

The same 91 executed checks passed separately on Python 3.12.15 / SQLAlchemy 2.0.23 (`min-final.json`) and Python 3.13.9 / SQLAlchemy 2.0.46 (`current-final.json`), with zero skips and no source drift. These are overlapping selections, not 182 unique tests. Both receipts identify the exact command, runtime, environment, dependency HEAD, product/fixture hashes and unchanged generator bytes, then read the recorded verdict/hash back from disk.

Confirmed and repaired findings:
- `min-second.json` recorded successful planning over an explicit null legacy ownership tag. The author repaired key-presence handling; both final runs refuse it.
- `min-stable.json` and `min-valid-red-rollback.json` reproduce a valid apply failure on SQLAlchemy 2.0.23: ORM-annotated Table DML confused the ingestion `metadata` column with declarative `MetaData`. The latter receipt also proves claim/observation/audit rollback. Pure Table-column repair passes both final runtimes.

Executed persistence controls:
- Malformed direct request/evidence/policy/plan objects; bool/NaN/infinity; absent/unsigned/empty/self-submitted policy; Unicode blank operator/artifact fields; stale/future/mismatched artifacts; live/uncertain signed writer states; wrong version/hash/backend/time and elapsed-time fence-release policy all refuse.
- A genuinely new TCP session is refused by closed database admission. A separate OS process trying to reopen admission times out while the same pg_database row is locked FOR SHARE.
- Valid native reconciliation preserves all original acquired/entered/entry/returned/job evidence and a subsequent native enter_domain/acknowledge/close path succeeds.
- Valid truly untagged legacy RUNNING observations receive FAILED status plus one audit, preserve preexisting metadata/errors and invent no claim.
- A public effect-table change after the signed census refuses apply and retains the RUNNING observation/claim with no audit.
- Actual `python -m seeding.reconcile_operator` backend termination before apply returns uncertain and retains ownership. Actual SIGKILL after planning followed by restart refuses the old backend plan.
- Actual backend termination during an UPDATE paused by an owned pg_sleep trigger returns uncertain; claim, job and audit mutations all roll back together.
- Explicitly injected report-boundary loss wraps real operator.main and real apply_plan, exiting only after the actual commit succeeds and before reporting. Independent readback finds one durable audit/released claim/FAILED job; a new operator session refuses the old plan. This injected reporting boundary is not runtime acquisition or exclusion proof.

Earlier attempts remain honestly classified:
- `min-first.json`: FAILED verifier fixture setup after 69 checks (SQLAlchemy interpreted a literal JSON colon as a bind parameter). Original generator retained; v2 fixed only that fixture.
- `min-second.json`: FAILED; null-tag finding plus product source drift invalidated the subsequent plan. The finding remains a red receipt, not acceptance evidence.
- `min-third.json`: FAILED due product source drift, after confirming repaired null-tag refusal. No acceptance claim.
- `min-stable.json` / `min-valid-red-rollback.json`: FAILED valid-operation compatibility controls, with stable product source.
- `min-fixed.json` / `current-fixed.json`: PASSED earlier overlapping 82-check selection; final 91-check receipts are the complete current selection.

Limitations: these fixtures do not certify production provider/pooler behavior, deployed writer inventory, actual host/scheduler/effects attestations, operational fence feasibility, or external role admission control. Parent separately owns actual native CLI/worker/adapter process acquisition races, migration/RLS/grants and integration checks. No financial/provider/storage/API calls were made. No GitHub writes, commits or pushes were made by this verifier. All verifier-owned databases/processes were cleaned; temporary local policy/IO files were removed while receipts and immutable generators remain.
'''
    generator=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    provenance={'generated_by':str(Path(__file__).relative_to(ROOT)),'generator_sha256':generator,'generated_at':datetime.now(timezone.utc).isoformat(),'target_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'final_receipts':['min-final.json','current-final.json'],'source_sha256':sources,'verified_generator_count':len(loaded),'owned_database_census':[],'temporary_fixture_directories_removed':removed,'verdict':'PASSED','unique_checks':91,'runtime_executions':2,'limitations':'Owned inert local fixture verification only; no production attestation.'}
    output=DIRECTORY/'final-summary.json';assert not output.exists();output.write_text(json.dumps(provenance,indent=2)+'\n')
    readback=json.loads(output.read_text());assert readback['generator_sha256']==generator;assert readback['verdict']=='PASSED'
    (DIRECTORY/'REPORT.md').write_text(message+'\nGenerated by `'+provenance['generated_by']+'`, SHA256 `'+generator+'`; source provenance in `final-summary.json`.\n')
    print(json.dumps({k:provenance[k] for k in ('verdict','unique_checks','runtime_executions','verified_generator_count','owned_database_census','source_sha256')},indent=2))
    return 0

if __name__=='__main__':sys.exit(main())
