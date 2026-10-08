"""Explicit bounded process port: python -m social.media.maintenance.

Importing this module starts no scheduler, loads no .env and makes no provider
request. Cleanup is opt-in; report-only is the default. No reconciliation proof
is fabricated by this runner or the production media runtime.
"""
import json

from sqlalchemy.orm import sessionmaker

from ..service import SocialError
from ..worker.config import WorkerConfig, create_worker_engine
from .cli import CLIInputError, PrivateArgumentParser, bounded_arguments
from .contracts import MaintenanceResult
from .runtime import media_runtime
from .service import MediaService
from .operator import prepare_reconciliation


def run_once(session_factory, runtime, *, allow_cleanup=False, limit=20):
    if type(allow_cleanup) is not bool or type(limit) is not int or not 1 <= limit <= 20:
        raise SocialError('INVALID_REQUEST', 'Maintenance must use a Boolean opt-in and a batch of one to twenty.', 422)
    with session_factory() as db:
        service = MediaService(db, runtime)
        cleaned = service.cleanup(limit) if allow_cleanup else 0
        return MaintenanceResult(cleanup_enabled=allow_cleanup, cleaned=cleaned, backlog=service.backlog())


def report_once(session_factory, runtime, *, limit=20, after_asset_id=None):
    # Validate before opening a connection, including direct operator callers.
    from uuid import UUID
    if type(limit) is not int or not 1 <= limit <= 20 or (after_asset_id is not None and type(after_asset_id) is not UUID):
        raise SocialError('INVALID_REQUEST', 'Use a batch of one to twenty and an optional UUID cursor.', 422)
    with session_factory() as db:
        return prepare_reconciliation(MediaService(db, runtime), limit=limit, after_asset_id=after_asset_id)


def main(argv=None):
    parser = PrivateArgumentParser(description='One bounded private-media maintenance batch; cleanup requires explicit opt-in.')
    parser.add_argument('--database-url', required=True, help='Explicit PostgreSQL DSN; no implicit application DSN or .env')
    parser.add_argument('--allow-cleanup', action='store_true', help='Delete only eligible settled quarantine/orphan bytes; retain ready originals')
    parser.add_argument('--once', action='store_true', help='Run one batch (all invocations are bounded to one batch)')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--prepare-reconciliation', action='store_true', help='Read-only upload/epoch and ledger observations; supplies no settlement authority')
    parser.add_argument('--after-asset-id', help='UUID cursor for a new read-only page; each page is a separate observation')
    engine = None
    try:
        args = parser.parse_args(bounded_arguments(argv))
        if not 1 <= args.limit <= 20:
            raise SocialError('INVALID_REQUEST', 'Maintenance batch must be between one and twenty.', 422)
        if (args.allow_cleanup and args.prepare_reconciliation
                or args.after_asset_id is not None and not args.prepare_reconciliation):
            raise SocialError('INVALID_REQUEST', 'Reconciliation preparation is read-only and cannot be combined with cleanup.', 422)
        from uuid import UUID
        cursor = UUID(args.after_asset_id) if args.after_asset_id is not None else None
        engine = create_worker_engine(WorkerConfig(database_url=args.database_url))
        factory, runtime = sessionmaker(engine, expire_on_commit=False), media_runtime()
        result = report_once(factory, runtime, limit=args.limit, after_asset_id=cursor) if args.prepare_reconciliation else run_once(factory, runtime, allow_cleanup=args.allow_cleanup, limit=args.limit)
        print(result.model_dump_json())
        return 0
    except Exception as error:
        # Database/SDK exception strings can contain DSNs, object keys or grants.
        code = error.code if isinstance(error, SocialError) else 'MEDIA_MAINTENANCE_INPUT_REFUSED' if isinstance(error, CLIInputError) else 'MEDIA_MAINTENANCE_FAILED'
        print(json.dumps({'error_code': code}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
