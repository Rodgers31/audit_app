"""Rehearsal-only observation/delay seams; never installed in the backend image.

The supervisor still executes its fixed native CLI and Gunicorn commands. No
adapter, SDK, authority, role verifier, queue or release implementation is replaced.
"""
import os
import sys

if os.environ.get('B15_REHEARSAL') == 'isolated' and 'social.worker' in sys.orig_argv:
    import json
    import time
    from social.worker.native_runtime import NativeRegistration
    from social.worker import startup

    def mark(stage, **fields):
        print(json.dumps(dict(rehearsal_stage=stage, pid=os.getpid(),
                              monotonic=time.monotonic(), **fields)), flush=True)

    original_create = startup.create_native_registration

    def create(*args, **kwargs):
        from pathlib import Path
        mark('native_constructing')
        if os.environ.get('B15_START_GATE') == 'true':
            while not Path('/evidence/start-release').exists():
                time.sleep(0.02)
        time.sleep(float(os.environ.get('B15_START_DELAY', '0')))
        result = original_create(*args, **kwargs)
        mark('native_constructed')
        return result

    startup.create_native_registration = create
    original_close = NativeRegistration.close

    async def close(self):
        import asyncio
        from pathlib import Path
        mark('native_closing')
        if os.environ.get('B15_CLOSE_GATE') == 'true':
            while not Path('/evidence/close-release').exists():
                await asyncio.sleep(0.02)
        await asyncio.sleep(float(os.environ.get('B15_CLOSE_DELAY', '0')))
        await original_close(self)
        mark('native_closed')

    NativeRegistration.close = close

    # Observe the real botocore HTTP pools closing too, including web ownership.
    from botocore.client import BaseClient
    original_sdk_close = BaseClient.close

    def sdk_close(self):
        original_sdk_close(self)
        mark('sdk_closed')

    BaseClient.close = sdk_close

    from social.worker.runner import SocialWorker
    original_worker_init = SocialWorker.__init__

    def worker_init(self, repository, **kwargs):
        original_worker_init(self, repository, **kwargs)
        mark('worker_budgets', external_slots=self.config.external_slots,
             executor_threads=self.executor._max_workers,
             pool_size=repository.engine.pool.size(),
             max_overflow=repository.engine.pool._max_overflow,
             idle_scan_seconds=self.config.idle_scan_seconds)

    SocialWorker.__init__ = worker_init
    original_run = SocialWorker.run

    async def run(self, **kwargs):
        import asyncio
        from pathlib import Path
        if os.environ.get('B15_RUN_GATE') == 'true':
            mark('worker_run_waiting')
            while not Path('/evidence/run-release').exists():
                await asyncio.sleep(0.02)
        return await original_run(self, **kwargs)

    SocialWorker.run = run
