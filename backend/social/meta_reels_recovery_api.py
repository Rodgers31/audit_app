"""Existing administrator authority for Meta-specific audited record-existing."""
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from .http_boundary import IdempotencyKey, NO_STORE, SocialRoute, social_admin
from .meta_reels_recovery import (MetaReelsRecoveryService, ProposeReelProof, RecordExistingReel,
                                  ReelProofContext, ReelProofDTO, ReelSettlementDTO)
from .service import SocialError
if __package__=='backend.social':
    from ..database import get_db
    from ..supabase_auth import AdminUser
else:
    from database import get_db
    from supabase_auth import AdminUser

router=APIRouter(prefix='/api/v1/admin/social/targets',tags=['Admin Social'],dependencies=[Depends(social_admin)],route_class=SocialRoute)


def service(db: Session=Depends(get_db)):
    return MetaReelsRecoveryService(db)


Service=Annotated[MetaReelsRecoveryService,Depends(service)]
Admin=Annotated[AdminUser,Depends(social_admin)]


def command(request,svc,admin,key,body,action,model,status=200):
    try:
        actor=UUID(admin.id)
    except (ValueError,TypeError,AttributeError):
        raise SocialError('PERMISSION_DENIED','A valid administrator UUID is required.',403) from None
    code,result=svc.command(actor=actor,route=request.method+' '+request.url.path,key=key,body=body.model_dump(mode='json'),
        request_id=request.state.social_request_id,action=action,status=status)
    return JSONResponse(status_code=code,content=model.model_validate(result).model_dump(mode='json'),headers=NO_STORE)


@router.get('/{target_id}/meta-reels/public-proof',response_model=ReelProofContext)
def proof_context(target_id:UUID,svc:Service):
    return svc.context(target_id)


@router.post('/{target_id}/meta-reels/public-proof',response_model=ReelProofDTO,status_code=201)
def propose(target_id:UUID,request:Request,body:ProposeReelProof,svc:Service,admin:Admin,key:IdempotencyKey):
    return command(request,svc,admin,key,body,lambda:svc.propose(target_id,body),ReelProofDTO,201)


@router.post('/{target_id}/meta-reels/record-existing',response_model=ReelSettlementDTO)
def record_existing(target_id:UUID,request:Request,body:RecordExistingReel,svc:Service,admin:Admin,key:IdempotencyKey):
    return command(request,svc,admin,key,body,lambda:svc.record_existing(target_id,body),ReelSettlementDTO)
