"""Prepare bounded read-only observation commands; never dispatch or accept a run."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
from seeding.source_plan import build_plan, DAILY, WEEKLY

KINDS = ('full15', 'replay', 'daily', 'weekly')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def prepare(kind, run_id, attempt, source_sha, *, cra='false', opendata='false',
            county_borrowing='false', discovery='false', replay_of=None):
    require(kind in KINDS, 'unknown observation kind')
    require(type(run_id) is str and re.fullmatch('[1-9][0-9]{0,17}',run_id), 'run identity required')
    require(type(attempt) is str and re.fullmatch('[1-9][0-9]{0,4}',attempt), 'attempt identity required')
    require(type(source_sha) is str and re.fullmatch('[0-9a-f]{40}',source_sha), 'source identity required')
    require(all(type(v) is str and v in ('true','false') for v in (cra,opendata,county_borrowing,discovery)), 'literal source opt-ins required')
    if kind != 'weekly':
        require((cra,opendata,county_borrowing,discovery)==('false',)*4, 'ordinary full15 cannot silently widen')
    if kind == 'replay':
        require(type(replay_of) is str and re.fullmatch('[1-9][0-9]{0,17}',replay_of) and replay_of!=run_id, 'distinct original replay run required')
    else:
        require(replay_of is None, 'replay identity only applies to replay')
    schedule = DAILY if kind=='daily' else WEEKLY if kind=='weekly' else ''
    plan = build_plan(event='schedule' if schedule else 'workflow_dispatch', schedule=schedule,
        domain='',dry_run='false',bootstrap='false',cra=cra,opendata=opendata,
        county_borrowing=county_borrowing,discovery=discovery)
    value=asdict(plan)
    identity=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    prefix=f'repos/Rodgers31/audit_app/actions/runs/{run_id}/attempts/{attempt}'
    commands=[['gh','api',prefix],['gh','api','--paginate','--slurp',prefix+'/jobs?per_page=100'],
              ['gh','api',prefix+'/logs']]
    paths=['backend/seeding/source_plan.py','backend/seeding/registries.py',
           'scripts/verification/nightly_workflow/refresh.py','frontend/lib/revalidation/paths.json']
    return {'schema':'nightly-observation-preparation-v1','generated_by':str(Path(__file__).resolve()),
        'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'at':datetime.now(timezone.utc).isoformat(),'verdict':'PREPARED_NOT_EXECUTED_NOT_ACCEPTED',
        'production_accepted':False,'kind':kind,'run_id':run_id,'attempt':attempt,'source_sha':source_sha,
        'event':'schedule' if schedule else 'workflow_dispatch','schedule':schedule,'plan':value,'plan_sha256':identity,
        'opt_ins':dict(cra=cra,opendata=opendata,county_borrowing=county_borrowing,discovery=discovery),
        'replay_of':replay_of,'read_only_capture_argv':commands,
        'source_inputs':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths},
        'capture_contract':[
            'Exact run/attempt/source/admitted revision; nonempty complete job and step inventory; zero-job/empty rollup refuses execution acceptance.',
            'Plan digest, CLI start/finish/exit/job floor and exact PG job IDs; actual schema/role/TLS/runtime/native identities.',
            'Per-domain component content/coverage/retention and original acquisition/readback authority; curated learning_hub stays a reference.',
            'Original nightly-refresh-v2 request/response base64 and HMAC verification on existing secret arrangement; no secret values in packet.',
            'Stable actual serving-container web census and generation adoption precedes exact allowed page acknowledgments; verify single-instance topology separately.',
            'Execution, stored integrity, source coverage, evidence retention and cache/page freshness have independent verdicts.',
            'Acquired originals and earlier refresh evidence survive later failures within existing storage budgets.',
            'Replay compares exact original source/component/runtime/row/lineage/cache identities with a distinct run; no duplicate facts/origins/social drafts.',
            'Weekly bootstrap and enabled opt-in domains require a distinct typed importer; ordinary full15 cannot substitute.',
            'Existing incident888 dedup/semantic transitions and channel delivery evidence are separate. Issue mutation alone never proves delivery.',
            'Owned-resource absence, all OFF controls, artifact/schema/admission binding, release and source authority remain separate gates.'],
        'holds':['runtime/profile and acceptance importer frozen deliveries','combined exact-tree/native/PG qualification',
                 'authorized release/admission/source decisions before operational execution','scheduled/full15/replay/weekly acceptance not executed'],
        'schedule_context':'02UTC ordinary Mon-Sat = preceding Chicago20:00; Sunday03UTC = Saturday21:00 on 2026-11-05; queue delay measured separately'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind',choices=KINDS,required=True)
    for field in ('run-id','attempt','source-sha'):
        parser.add_argument('--'+field,required=True)
    for field in ('cra','opendata','county-borrowing','discovery'):
        parser.add_argument('--'+field,choices=('true','false'),default='false')
    parser.add_argument('--replay-of')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        output=args.output
        require(output.is_absolute() and not output.exists() and not output.is_symlink(), 'fresh absolute external output required')
        require(not output.parent.resolve(strict=True).is_relative_to(ROOT), 'source output refused')
        for parent in output.parents:
            require(not parent.is_symlink(), 'linked output parent refused')
        value=prepare(args.kind,args.run_id,args.attempt,args.source_sha,cra=args.cra,opendata=args.opendata,
            county_borrowing=args.county_borrowing,discovery=args.discovery,replay_of=args.replay_of)
        with output.open('x') as stream:
            json.dump(value,stream,indent=2,allow_nan=False)
        require(json.loads(output.read_text())==value,'preparation disk readback refused')
        print(value['verdict'])
        return 0
    except (ValueError,OSError) as exc:
        print('Observation preparation refused: '+str(exc),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
