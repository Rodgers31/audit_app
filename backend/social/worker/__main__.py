"""Explicit separate provider entry; no import of FastAPI or web schedulers."""
import asyncio
import json
import logging
import os
import re
import signal
import threading
from uuid import uuid4

from sqlalchemy import text

from .arguments import PrivateArgumentParser
from .config import WorkerConfig, create_worker_engine
from .ownership import acquire_authority
from .repository import QueueRepository
from .role_contract import verify_worker_role
from .runner import SocialWorker
from .startup import native_runtime, validate_worker_native_environment


def main(argv=None):
    parser = PrivateArgumentParser(description='Explicit durable social worker; native providers require validated opt-in')
    database = parser.add_mutually_exclusive_group(required=True)
    database.add_argument('--database-url')
    database.add_argument('--database-url-env')
    parser.add_argument('--worker-role')
    parser.add_argument('--database-schema')
    parser.add_argument('--deployment-version', default='batch-1')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--native-meta', action='store_true')
    parser.add_argument('--native-platforms', action='store_true')
    parser.add_argument('--supervisor-receipt-fd', type=int)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    engine, worker, authority = None, None, None
    result = 0
    stopped = threading.Event()
    installed = {}
    resources_closed = False
    wake_read, wake_write = None, None

    def stop(signum, frame):
        stopped.set()
        if worker is not None:
            worker.stop()
        try:
            os.write(wake_write, b'x')
        except BlockingIOError:
            pass  # A full pipe already guarantees a pending selector wakeup.

    try:
        wake_read, wake_write = os.pipe()
        os.set_blocking(wake_read, False)
        os.set_blocking(wake_write, False)
        database_url = args.database_url
        if args.database_url_env is not None:
            if re.fullmatch(r'[A-Z][A-Z0-9_]{0,127}', args.database_url_env) is None:
                raise ValueError()
            database_url = os.environ.get(args.database_url_env)
        native = args.native_meta or args.native_platforms
        if native and not args.worker_role:
            raise ValueError()
        if args.supervisor_receipt_fd is not None and args.supervisor_receipt_fd < 3:
            raise ValueError()
        schema = args.database_schema or ('public' if args.worker_role else None)
        config = WorkerConfig(database_url, deployment_version=args.deployment_version, database_schema=schema)
        for sig in (signal.SIGTERM, signal.SIGINT):
            installed[sig] = signal.getsignal(sig)
            signal.signal(sig, stop)
        engine = create_worker_engine(config)
        if args.worker_role:
            if args.native_platforms:
                verify_worker_role(engine, args.worker_role, schema, platforms=True)
            else:
                verify_worker_role(engine, args.worker_role, schema)
        if not native:
            # This diagnostic has no adapters, claims, recovery or resident loop.
            if not args.once:
                raise ValueError()
            with engine.connect() as conn:
                if conn.execute(text('SELECT EXISTS(SELECT 1 FROM social_post_targets)')).scalar_one():
                    raise ValueError()
        else:
            if not args.native_platforms:
                from ..platform_runtime import load_platform_settings
                if any(item.ready for item in load_platform_settings(os.environ).adapters.values()):
                    raise ValueError('Native platform configuration requires explicit CLI opt-in')
            validate_worker_native_environment(os.environ)
            if stopped.is_set():
                raise RuntimeError('Stopped before acquisition')
            owner_id = uuid4()
            authority = acquire_authority(engine, owner_id, config.deployment_version)
            repository = QueueRepository(engine, config, owner_id, authority=authority)

            async def execute():
                nonlocal worker, resources_closed
                interrupted = False
                def wake():
                    try:
                        os.read(wake_read, 4096)
                    except BlockingIOError:
                        pass  # Another coalesced callback drained the same wakeup.
                asyncio.get_running_loop().add_reader(wake_read, wake)
                # Retain ownership on every startup or closure failure.
                repository.check_authority()
                try:
                    async with native_runtime(engine) as registration:
                        if registration is None:
                            raise ValueError()
                        worker = SocialWorker(repository, adapters=registration.adapters,
                            credential_loader=registration.credential_loader, media_access=registration.media_access)
                        try:
                            # This CLI owns its asyncio.run loop. Material/DNS
                            # offloads share the DB executor's two-thread budget.
                            asyncio.get_running_loop().set_default_executor(worker.executor)
                            if stopped.is_set():
                                worker.stop()
                            await worker.run(once=args.once)
                        except KeyboardInterrupt:
                            interrupted = True
                            raise
                        finally:
                            try:
                                await worker.close()
                            except KeyboardInterrupt:
                                interrupted = True
                                raise
                        if worker.failed:
                            raise RuntimeError('Worker unavailable')
                finally:
                    if interrupted:
                        raise KeyboardInterrupt() from None
                if not repository.drained():
                    raise RuntimeError('Durable worker drain is unresolved')
                resources_closed = True
            asyncio.run(execute())
    except KeyboardInterrupt:
        logging.getLogger('social.worker').error('{"event":"worker_startup_interrupted","error_code":"WORKER_UNAVAILABLE"}')
        result = 130
    except (Exception, asyncio.CancelledError):
        logging.getLogger('social.worker').error('{"event":"worker_startup_failed","error_code":"WORKER_UNAVAILABLE"}')
        result = 1
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except KeyboardInterrupt:
                logging.getLogger('social.worker').error('{"event":"worker_shutdown_interrupted","error_code":"WORKER_UNAVAILABLE"}')
                result = 130
            except (Exception, asyncio.CancelledError):
                logging.getLogger('social.worker').error('{"event":"worker_shutdown_failed","error_code":"WORKER_UNAVAILABLE"}')
                if result != 130:
                    result = 1
        if result == 0 and resources_closed and authority is not None and args.supervisor_receipt_fd is not None:
            try:
                proof = dict(version=1, owner_id=str(authority.owner_id), generation=authority.generation,
                             providers_closed=True, executor_closed=True, claims_drained=True)
                os.write(args.supervisor_receipt_fd, json.dumps(proof, separators=(',', ':')).encode())
            except (Exception, asyncio.CancelledError):
                logging.getLogger('social.worker').error('{"event":"worker_receipt_failed","error_code":"WORKER_UNAVAILABLE"}')
                result = 1
        for sig, handler in installed.items():
            try:
                signal.signal(sig, handler)
            except KeyboardInterrupt:
                logging.getLogger('social.worker').error('{"event":"worker_shutdown_interrupted","error_code":"WORKER_UNAVAILABLE"}')
                result = 130
            except (Exception, asyncio.CancelledError):
                logging.getLogger('social.worker').error('{"event":"worker_shutdown_failed","error_code":"WORKER_UNAVAILABLE"}')
                if result != 130:
                    result = 1
        for fd in (wake_read, wake_write):
            if fd is not None:
                try:
                    os.close(fd)
                except (OSError, asyncio.CancelledError):
                    logging.getLogger('social.worker').error('{"event":"worker_shutdown_failed","error_code":"WORKER_UNAVAILABLE"}')
                    if result != 130:
                        result = 1
    return result


if __name__ == '__main__':
    raise SystemExit(main())
