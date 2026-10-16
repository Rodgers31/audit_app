"""Explicit separate entrypoint: python -m social.worker --database-url ..."""
import asyncio
from contextlib import AsyncExitStack
import logging
import os
import re
import signal
import sys
from uuid import uuid4

from .config import WorkerConfig, create_worker_engine
from .arguments import PrivateArgumentParser
from .repository import QueueRepository
from .runner import SocialWorker
from .startup import native_runtime
from .role_contract import verify_worker_role


def main(argv=None):
    parser = PrivateArgumentParser(description="Explicit durable social worker; native providers require separate validated opt-in")
    database = parser.add_mutually_exclusive_group(required=True)
    database.add_argument("--database-url", help="Explicit PostgreSQL DSN; .env is never loaded")
    database.add_argument("--database-url-env", help="Name of the explicit DSN environment variable; keeps credentials out of argv")
    parser.add_argument("--worker-role", help="Existing restricted LOGIN role; required for native providers")
    parser.add_argument("--database-schema", help="Trusted schema pinned on every connection; defaults to public with --worker-role")
    parser.add_argument("--deployment-version", default="batch-1")
    parser.add_argument("--once", action="store_true", help="One bounded scan then exit")
    parser.add_argument("--native-meta", action="store_true", help="Use the explicitly enabled and operationally verified Meta registration")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    engine = None
    result = 0
    try:
        database_url = args.database_url
        if args.database_url_env is not None:
            if re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}', args.database_url_env) is None:
                raise ValueError()
            database_url = os.environ.get(args.database_url_env)
        if args.native_meta and not args.worker_role:
            raise ValueError()
        schema = args.database_schema
        if schema is None and args.worker_role is not None:
            schema = "public"
        config = WorkerConfig(database_url, deployment_version=args.deployment_version,
                              database_schema=schema)
        engine = create_worker_engine(config)
        if args.worker_role is not None:
            verify_worker_role(engine, args.worker_role, schema)
        repository = QueueRepository(engine, config, uuid4())
        async def execute():
            interrupted = False
            try:
                async with AsyncExitStack() as stack:
                    try:
                        registration = await stack.enter_async_context(native_runtime(engine)) if args.native_meta else None
                        if args.native_meta and registration is None:
                            raise ValueError('Native providers are disabled')
                        worker = SocialWorker(repository,
                            adapters=registration.adapters if registration else None,
                            credential_loader=registration.credential_loader if registration else None,
                            media_access=registration.media_access if registration else None)
                        loop = asyncio.get_running_loop()
                        installed_signals = []
                        try:
                            for sig in (signal.SIGTERM, signal.SIGINT):
                                loop.add_signal_handler(sig, worker.stop)
                                installed_signals.append(sig)
                            await worker.run(once=args.once)
                        finally:
                            failed = False
                            cancelled = isinstance(sys.exc_info()[1], asyncio.CancelledError)
                            interrupted = isinstance(sys.exc_info()[1], KeyboardInterrupt)
                            for sig in installed_signals:
                                try:
                                    loop.remove_signal_handler(sig)
                                except KeyboardInterrupt:
                                    interrupted = True
                                except asyncio.CancelledError:
                                    cancelled = True
                                except Exception:
                                    failed = True
                            try:
                                await worker.close()
                            except KeyboardInterrupt:
                                interrupted = True
                            except asyncio.CancelledError:
                                cancelled = True
                            except Exception:
                                failed = True
                            if interrupted:
                                raise KeyboardInterrupt()
                            if cancelled:
                                raise asyncio.CancelledError()
                            if failed:
                                raise RuntimeError('Worker shutdown failed')
                    except KeyboardInterrupt:
                        interrupted = True
                        raise
            finally:
                # Native context exit may itself fail; it cannot turn a pending
                # user interrupt into a different exit status/private traceback.
                if interrupted:
                    raise KeyboardInterrupt()
        asyncio.run(execute())
    except Exception:
        # Driver exceptions may include connection strings or sensitive parameters.
        logging.getLogger("social.worker").error('{"event":"worker_startup_failed","error_code":"WORKER_UNAVAILABLE"}')
        result = 1
    except KeyboardInterrupt:
        # An interrupt traceback would carry SQL and driver text; keep it fixed.
        logging.getLogger("social.worker").error('{"event":"worker_startup_interrupted","error_code":"WORKER_UNAVAILABLE"}')
        result = 130
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except KeyboardInterrupt:
                logging.getLogger('social.worker').error('{"event":"worker_shutdown_interrupted","error_code":"WORKER_UNAVAILABLE"}')
                result = 130
            except Exception:
                logging.getLogger('social.worker').error('{"event":"worker_shutdown_failed","error_code":"WORKER_UNAVAILABLE"}')
                if result != 130:
                    result = 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
