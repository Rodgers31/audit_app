"""Explicit bounded process port: python -m social.media.maintenance.

Importing this module starts no scheduler, loads no .env and makes no provider
request. Cleanup is opt-in; report-only is the default. No reconciliation proof
is fabricated by this runner or the production media runtime.
"""
import argparse
import json

from sqlalchemy.orm import sessionmaker

from ..service import SocialError
from ..worker.config import WorkerConfig, create_worker_engine
from .contracts import MaintenanceResult
from .runtime import media_runtime
from .service import MediaService


def run_once(session_factory, runtime, *, allow_cleanup=False, limit=20):
    if type(allow_cleanup) is not bool or type(limit) is not int or not 1 <= limit <= 20:
        raise SocialError('INVALID_REQUEST', 'Maintenance must use a Boolean opt-in and a batch of one to twenty.', 422)
    with session_factory() as db:
        service = MediaService(db, runtime)
        cleaned = service.cleanup(limit) if allow_cleanup else 0
        return MaintenanceResult(cleanup_enabled=allow_cleanup, cleaned=cleaned, backlog=service.backlog())


def main(argv=None):
    parser = argparse.ArgumentParser(description='One bounded private-media maintenance batch; cleanup requires explicit opt-in.')
    parser.add_argument('--database-url', required=True, help='Explicit PostgreSQL DSN; no implicit application DSN or .env')
    parser.add_argument('--allow-cleanup', action='store_true', help='Delete only eligible settled quarantine/orphan bytes; retain ready originals')
    parser.add_argument('--once', action='store_true', help='Run one batch (all invocations are bounded to one batch)')
    parser.add_argument('--limit', type=int, default=20)
    args = parser.parse_args(argv)
    engine = None
    try:
        if not 1 <= args.limit <= 20:
            raise SocialError('INVALID_REQUEST', 'Maintenance batch must be between one and twenty.', 422)
        engine = create_worker_engine(WorkerConfig(database_url=args.database_url))
        result = run_once(sessionmaker(engine, expire_on_commit=False), media_runtime(), allow_cleanup=args.allow_cleanup, limit=args.limit)
        print(result.model_dump_json())
        return 0
    except Exception as error:
        # Database/SDK exception strings can contain DSNs, object keys or grants.
        print(json.dumps({'error_code': error.code if isinstance(error, SocialError) else 'MEDIA_MAINTENANCE_FAILED'}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
