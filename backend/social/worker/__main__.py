"""Explicit separate entrypoint: python -m social.worker --database-url ..."""
import argparse
import asyncio
from contextlib import AsyncExitStack
import logging
import signal
import sys
from uuid import uuid4

from .config import WorkerConfig, create_worker_engine
from .repository import QueueRepository
from .runner import SocialWorker
from .startup import native_runtime


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explicit durable social worker; native providers require separate validated opt-in")
    parser.add_argument("--database-url", required=True, help="Explicit PostgreSQL DSN; .env is never loaded")
    parser.add_argument("--deployment-version", default="batch-1")
    parser.add_argument("--once", action="store_true", help="One bounded scan then exit")
    parser.add_argument("--native-meta", action="store_true", help="Use the explicitly enabled and operationally verified Meta registration")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    engine = None
    result = 0
    try:
        config = WorkerConfig(args.database_url, deployment_version=args.deployment_version)
        engine = create_worker_engine(config)
        repository = QueueRepository(engine, config, uuid4())
        async def execute():
            async with AsyncExitStack() as stack:
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
                    for sig in installed_signals:
                        try:
                            loop.remove_signal_handler(sig)
                        except asyncio.CancelledError:
                            cancelled = True
                        except Exception:
                            failed = True
                    try:
                        await worker.close()
                    except asyncio.CancelledError:
                        cancelled = True
                    except Exception:
                        failed = True
                    if cancelled:
                        raise asyncio.CancelledError()
                    if failed:
                        raise RuntimeError('Worker shutdown failed')
        asyncio.run(execute())
    except Exception:
        # Driver exceptions may include connection strings or sensitive parameters.
        logging.getLogger("social.worker").error('{"event":"worker_startup_failed","error_code":"WORKER_UNAVAILABLE"}')
        result = 1
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:
                logging.getLogger('social.worker').error('{"event":"worker_shutdown_failed","error_code":"WORKER_UNAVAILABLE"}')
                result = 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
