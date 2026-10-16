"""Direct-call adversaries retain one runtime's fixed external slot budget."""
import asyncio
from contextlib import contextmanager
from types import SimpleNamespace
import threading
from uuid import uuid4

import pytest

from social.contracts import CapabilitySet, OperationPlan, OperationResult, ResolvedPostPayload, ValidationResult
from social.worker.config import WorkerConfig
from social.worker.ownership import acquire_authority
from social.worker.repository import Claim, Intent
from social.worker.runner import SocialWorker


class AcquisitionResult:
    def __init__(self, statement):
        self.statement = str(statement)

    def scalar_one(self):
        return 1 if 'RETURNING generation' in self.statement else True

    def scalar_one_or_none(self):
        return True


class AcquisitionEngine:
    @contextmanager
    def begin(self):
        yield SimpleNamespace(execute=lambda statement, *args: AcquisitionResult(statement))


class InertAdapter:
    caps = CapabilitySet(eligible=True, supported_formats=('text',),
                         feature_states={'publishing': 'supported'}, price_class='free',
                         adapter_available=True, provider_api_version='inert')

    def __init__(self):
        self.active = self.peak = self.calls = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    def capabilities(self, snapshot):
        return self.caps

    def validate(self, *args):
        return ValidationResult(valid=True)

    def next_operation(self, payload, checkpoint):
        return OperationPlan(operation_id=uuid4(), operation='publish', publication_capable=True,
                             safe_replay_class='requires_reconciliation', checkpoint={})

    async def execute(self, *args):
        self.active += 1
        self.calls += 1
        self.peak = max(self.peak, self.active)
        self.entered.set()
        try:
            await self.release.wait()
        finally:
            self.active -= 1
        return OperationResult(outcome='confirmed_success', primary_remote_id='inert',
                               visibility_state='public', confirmation_kind='synthetic')


class InertRepository:
    config = WorkerConfig('postgresql://inert@localhost/inert', external_slots=1)

    def __init__(self):
        self.authority = acquire_authority(AcquisitionEngine(), uuid4(), 'inert-runtime-test')
        self.worker_id = str(self.authority.owner_id)
        self.admission_stopped = threading.Event()
        self.claim_calls = self.intents = 0

    def validate_schema(self):
        pass

    def recover_expired(self):
        pass

    def heartbeat(self, **kwargs):
        pass

    def claim_due(self, limit):
        self.claim_calls += 1
        assert limit == 1
        return [Claim(str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4()), 1, 'queued')]

    def load(self, claim):
        payload = ResolvedPostPayload(account_id=claim.account_id, platform='facebook', api_product='inert',
                                      external_account_id='123', format='text', text='inert',
                                      evidence_hash='a'*64, content_hash='b'*64)
        return dict(resolved_payload=payload.model_dump(mode='json'), checkpoint={}, remote_refs={},
                    capability_snapshot=InertAdapter.caps.model_dump(mode='json'),
                    admitted_credential_id=None, admitted_credential_version=None)

    def begin_operation(self, claim, **kwargs):
        self.intents += 1
        return Intent(str(kwargs['operation_id']), 1, None)

    def finish(self, *args, **kwargs):
        return True


def test_concurrent_run_cannot_claim_twice_with_one_runtime():
    async def exercise():
        repo, adapter = InertRepository(), InertAdapter()
        worker = SocialWorker(repo, adapters={('facebook', 'inert'): adapter})
        first = asyncio.create_task(worker.run(once=True))
        try:
            await asyncio.wait_for(adapter.entered.wait(), 2)
            second = asyncio.create_task(worker.run(once=True))
            # A reentrant call must refuse before a second scan or claim.
            await asyncio.sleep(0)
            assert second.done(), 'Reentrant run entered the resident scan loop'
            with pytest.raises(RuntimeError, match='already running'):
                await second
            assert repo.claim_calls == 1 and repo.intents == 1
        finally:
            adapter.release.set()
            await asyncio.gather(first, *([second] if 'second' in locals() else []), return_exceptions=True)
            await worker.close()
    asyncio.run(exercise())


def test_direct_process_calls_obey_external_slots_and_stop_queued_admission():
    async def exercise():
        repo, adapter = InertRepository(), InertAdapter()
        worker = SocialWorker(repo, adapters={('facebook', 'inert'): adapter})
        claims = [Claim(str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4()), i, 'queued') for i in (1, 2)]
        first = asyncio.create_task(worker.process(claims[0]))
        second = None
        try:
            await asyncio.wait_for(adapter.entered.wait(), 2)
            second = asyncio.create_task(worker.process(claims[1]))
            # Force the competing operation through its DB awaits when unguarded.
            for _ in range(10):
                await asyncio.sleep(.01)
            assert adapter.peak == 1 and repo.intents == 1
            worker.stop()
        finally:
            adapter.release.set()
            await asyncio.gather(first, *([second] if second is not None else []))
            await worker.close()
        assert adapter.calls == 1 and repo.intents == 1
    asyncio.run(exercise())


def test_close_waits_for_direct_provider_call_before_unbinding_runtime():
    from social.worker.ownership import AuthorityLost

    async def exercise():
        repo, adapter = InertRepository(), InertAdapter()
        worker = SocialWorker(repo, adapters={('facebook', 'inert'): adapter})
        claim = Claim(str(uuid4()), str(uuid4()), str(uuid4()), str(uuid4()), 1, 'queued')
        process = asyncio.create_task(worker.process(claim))
        close = None
        try:
            await asyncio.wait_for(adapter.entered.wait(), 2)
            close = asyncio.create_task(worker.close())
            await asyncio.sleep(0)
            assert not close.done(), 'close returned while its directly invoked provider was active'
            successor_repo = InertRepository()
            successor_repo.authority = repo.authority
            successor_repo.worker_id = repo.worker_id
            with pytest.raises(AuthorityLost):
                SocialWorker(successor_repo)
        finally:
            adapter.release.set()
            await process
            if close is not None:
                await close
            else:
                await worker.close()
        assert adapter.active == 0 and adapter.calls == 1
    asyncio.run(exercise())
