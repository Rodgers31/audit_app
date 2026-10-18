"""A fresh monotonic epoch emits one initial heartbeat without extra polling."""
import asyncio
from dataclasses import replace
from types import SimpleNamespace

import pytest

import social.worker.runner as runner
from test_worker_runtime_bounds import InertRepository


@pytest.mark.parametrize('epoch', [0.0, 0.5, 60.0, 6000.0])
@pytest.mark.parametrize('interval', [15.0, 60.0])
def test_initial_heartbeat_then_exact_idle_cadence(monkeypatch, epoch, interval):
    clock = [epoch]
    monkeypatch.setattr(runner, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    offsets = [0, 0, interval - 0.001, interval, interval, 2 * interval - 0.001, 2 * interval]
    observations = []

    async def exercise():
        class Repository(InertRepository):
            def __init__(self):
                super().__init__()
                self.config = replace(self.config, idle_heartbeat_seconds=interval)
                self.index = -1

            def recover_expired(self):
                self.index += 1
                clock[0] = epoch + offsets[self.index]

            def claim_due(self, limit):
                return []

            def heartbeat(self, **values):
                observations.append((clock[0], values))

            def next_due_delay(self, delay):
                if self.index == len(offsets) - 1:
                    worker.stop()
                return 0  # Advance the owned fixture; no real waiting.

        repository = Repository()
        worker = runner.SocialWorker(repository)
        try:
            await worker.run()
        finally:
            await worker.close()

    asyncio.run(exercise())
    assert [(at, values['state']) for at, values in observations] == [
        (epoch, 'idle'), (epoch + interval, 'idle'),
        (epoch + 2 * interval, 'idle'), (epoch + 2 * interval, 'stopped'),
    ]
    assert all(values.get('scanned') is True for _, values in observations[:-1])
