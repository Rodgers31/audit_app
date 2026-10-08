"""Authenticated reconciliation is delivered through a durable worker intent."""
import asyncio
from social.contracts import ReconciliationResult
from social.worker.materials import CredentialLoadRequest
from social.worker.runner import SocialWorker
from test_queue_postgres import engine, repository, seed, FakeAdapter


def test_restart_reconciliation_receives_fresh_intent_bound_material(engine):
    seed(engine,state='reconciling')
    repo=repository(engine)
    material=object(); observed=[]
    async def load(request):
        assert isinstance(request,CredentialLoadRequest)
        assert request.mutating is False and request.operation_id
        observed.append(request)
        return material
    class AuthenticatedReadAdapter(FakeAdapter):
        async def reconcile(self,payload,checkpoint,attempt,credential,media_access):
            assert credential is material
            self.reconciliations += 1
            return ReconciliationResult(outcome='unknown',evidence={'verified_read':True})
    adapter=AuthenticatedReadAdapter()
    async def run():
        worker=SocialWorker(repo,adapters={('facebook','fake'):adapter},credential_loader=load)
        try:
            claims=await worker.db(repo.claim_due)
            await worker.process(claims[0])
        finally: await worker.close()
    asyncio.run(run())
    assert len(observed)==1 and adapter.reconciliations==1 and adapter.calls==0
