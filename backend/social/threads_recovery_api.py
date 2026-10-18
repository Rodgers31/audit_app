"""Admin-only, no-network operator proof commands for Threads."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .http_boundary import IdempotencyKey, NO_STORE, SocialRoute, social_admin
from .threads_recovery import (ProposePublicProof, PublicProofContext, PublicProofDTO,
                               RecordExisting, SettlementDTO, ThreadsRecoveryService)
from .service import SocialError
if __package__ == 'backend.social':
    from ..database import get_db
    from ..supabase_auth import AdminUser
else:
    from database import get_db
    from supabase_auth import AdminUser

router = APIRouter(prefix='/api/v1/admin/social', tags=['Admin Social'], dependencies=[Depends(social_admin)], route_class=SocialRoute)


def service(db: Session = Depends(get_db)):
    return ThreadsRecoveryService(db)


Service = Annotated[ThreadsRecoveryService, Depends(service)]
Admin = Annotated[AdminUser, Depends(social_admin)]


def command(request, svc, admin, key, body, action, model, status=200):
    try:
        actor = UUID(admin.id)
    except (TypeError, ValueError, AttributeError):
        raise SocialError('PERMISSION_DENIED', 'A valid administrator UUID is required.', 403) from None
    status, result = svc.command(actor=actor, route=request.method+' '+request.url.path, key=key,
        body=body.model_dump(mode='json'), request_id=request.state.social_request_id, action=action, status=status)
    return JSONResponse(status_code=status, content=model.model_validate(result).model_dump(mode='json'), headers=NO_STORE)


@router.get('/targets/{target_id}/public-proof', response_model=PublicProofContext)
def public_proof_context(target_id: UUID, svc: Service):
    return svc.context(target_id)


@router.post('/targets/{target_id}/public-proof', response_model=PublicProofDTO, status_code=201)
def propose_public_proof(target_id: UUID, request: Request, body: ProposePublicProof, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: svc.propose(target_id, body), PublicProofDTO, 201)


@router.post('/targets/{target_id}/record-existing', response_model=SettlementDTO)
def record_existing(target_id: UUID, request: Request, body: RecordExisting, svc: Service, admin: Admin, key: IdempotencyKey):
    return command(request, svc, admin, key, body, lambda: svc.record_existing(target_id, body), SettlementDTO)
