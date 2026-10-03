"""Explicit separate entrypoint: python -m social.worker --database-url ..."""
import argparse
import asyncio
import logging
import signal
from uuid import uuid4

from .config import WorkerConfig, create_worker_engine
from .repository import QueueRepository
from .runner import SocialWorker


def main(argv=None):
    parser = argparse.ArgumentParser(description="Durable social worker (no platform adapters in batch one)")
    parser.add_argument("--database-url", required=True, help="Explicit PostgreSQL DSN; .env is never loaded")
    parser.add_argument("--deployment-version", default="batch-1")
    parser.add_argument("--once", action="store_true", help="One bounded scan then exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        config = WorkerConfig(args.database_url, deployment_version=args.deployment_version)
        engine = create_worker_engine(config)
        repository = QueueRepository(engine, config, uuid4())
        worker = SocialWorker(repository)  # No fake or real providers registered.
        async def execute():
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, worker.stop)
            try:
                await worker.run(once=args.once)
            finally:
                await worker.close()
        try:
            asyncio.run(execute())
        finally:
            engine.dispose()
    except Exception:
        # Driver exceptions may include connection strings or sensitive parameters.
        logging.getLogger("social.worker").error('{"event":"worker_startup_failed","error_code":"WORKER_UNAVAILABLE"}')
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
