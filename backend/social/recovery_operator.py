"""Explicit local operator entry point: export/verify/rotate/reapply. Defaults refuse.

No dotenv, credentials discovery, network provisioning or external deletion. DB
URLs are read only from an explicitly named environment variable. Keys are private
operator-owned files. Outputs are new exclusive private paths; never overwritten.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from .connections.recovery import parse_keyring, read_keyring_backup
from .connections.rotation import rotate_retained_envelopes
from .privacy.private_io import read_private, write_private
from .privacy.restoration import reapply_deletion_ledger
from .recovery_database import export_database_backup, verify_database_restore, MAX_TOTAL_BYTES, MAX_MANIFEST


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('export','verify','rotate','reapply-ledger'))
    parser.add_argument('--database-url-env', required=True)
    parser.add_argument('--schema', default='public')
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--signing-key', type=Path)
    parser.add_argument('--trusted-public-key', type=Path)
    parser.add_argument('--pg-dump', type=Path)
    parser.add_argument('--current-keyring', type=Path)
    parser.add_argument('--candidate-keyring', type=Path)
    parser.add_argument('--digest-backup', type=Path)
    parser.add_argument('--subject-proofs', type=Path)
    parser.add_argument('--ledger-entry', type=Path, action='append', default=[])
    parser.add_argument('--apply', action='store_true', help='Explicitly apply local rotation/suppression; publication must remain paused.')
    args=parser.parse_args(argv)
    engine=None
    try:
        if not re.fullmatch('[A-Z][A-Z0-9_]{0,127}', args.database_url_env):
            raise ValueError()
        url=os.environ.get(args.database_url_env)
        if type(url) is not str or not url.startswith(('postgresql://','postgresql+psycopg2://')):
            raise ValueError()
        engine=create_engine(url, pool_size=2, max_overflow=0, connect_args={'connect_timeout':5})
        if args.operation=='export':
            if args.backup is None or args.manifest is None or args.signing_key is None or args.pg_dump is None or args.apply:
                raise ValueError()
            for path in (args.backup,args.manifest):
                if not path.is_absolute() or path.exists() or path.is_symlink():raise ValueError()
            if args.backup==args.manifest:raise ValueError()
            packet=export_database_backup(engine,schema=args.schema,destination=args.backup,signing_key=read_private(args.signing_key,32),pg_dump=args.pg_dump,
                keyring_backup=read_private(args.current_keyring,65536) if args.current_keyring else None,
                digest_backup=read_private(args.digest_backup,65536) if args.digest_backup else None)
            write_private(args.manifest,packet)
            result={'status':'EXPORTED_AND_SIGNED','scope':'complete_selected_schema_snapshot','backup_custody_verified':False,'production_authorized':False}
        elif args.operation=='verify':
            if args.backup is None or args.manifest is None or args.trusted_public_key is None or args.apply:raise ValueError()
            digest=hashlib.sha256(read_private(args.backup,MAX_TOTAL_BYTES)).hexdigest()
            result=verify_database_restore(engine,read_private(args.manifest,MAX_MANIFEST),schema=args.schema,public_key=read_private(args.trusted_public_key,32),backup_sha256=digest,
                keyring_backup=read_private(args.current_keyring,65536) if args.current_keyring else None,
                digest_backup=read_private(args.digest_backup,65536) if args.digest_backup else None,
                subject_proofs=read_private(args.subject_proofs,256000) if args.subject_proofs else None)
        elif args.operation=='rotate':
            if args.current_keyring is None or args.candidate_keyring is None or not args.apply:raise ValueError()
            current=read_keyring_backup(args.current_keyring).cipher()
            candidate=read_keyring_backup(args.candidate_keyring).cipher()
            with Session(engine) as db:result=rotate_retained_envelopes(db,old_cipher=current,candidate_cipher=candidate)
        else:
            if args.current_keyring is None or args.trusted_public_key is None or not 1<=len(args.ledger_entry)<=1000:raise ValueError()
            entries=[read_private(path,512_000) for path in args.ledger_entry]
            with Session(engine) as db:result=reapply_deletion_ledger(db,entries,public_key=read_private(args.trusted_public_key,32),cipher=read_keyring_backup(args.current_keyring).cipher(),apply=args.apply)
        print(json.dumps(result,sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({'status':'REFUSED','code':'RECOVERY_OPERATOR_REFUSED','production_authorized':False}))
        return 1
    finally:
        if engine is not None:engine.dispose()

if __name__=='__main__':
    raise SystemExit(main())
