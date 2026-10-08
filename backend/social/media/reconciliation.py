"""Internal operator evidence port. Storage metadata never proves write quiescence.

A trusted implementation must establish that previously admitted browser and
server writes are drained or irrevocably fenced. The production default has no
such capability. This port intentionally has no browser route or Boolean override.
"""
from datetime import datetime
from typing import Annotated, Optional, Protocol
from uuid import UUID

from pydantic import ConfigDict, Field

from ..contracts import Hash, PositiveVersion, StrictModel

Epoch = Annotated[int, Field(strict=True, ge=0)]


class ReconciliationModel(StrictModel):
    # Internal callers and injected verifiers may supply constructed/copied
    # models. Revalidate the whole tree before it can settle durable hazards.
    model_config = ConfigDict(revalidate_instances='always', hide_input_in_errors=True)


class WriteQuiescenceReceipt(ReconciliationModel):
    receipt_id: UUID
    evidence_hash: Hash


class WriteQuiescenceScope(ReconciliationModel):
    asset_id: UUID
    storage_provider: str
    bucket: str
    upload_version: PositiveVersion
    grant_epoch: Epoch
    grant_expires_at: Optional[datetime]
    finalization_epoch: Optional[PositiveVersion]


class WriteQuiescenceEvidence(ReconciliationModel):
    scope: WriteQuiescenceScope
    receipt: WriteQuiescenceReceipt
    verified_at: datetime


class ReconcileUpload(ReconciliationModel):
    expected_version: PositiveVersion
    expected_grant_epoch: Epoch
    expected_finalization_epoch: Optional[PositiveVersion]
    receipt: WriteQuiescenceReceipt


class WriteQuiescenceVerifier(Protocol):
    def verify(self, scope: WriteQuiescenceScope, receipt: WriteQuiescenceReceipt) -> Optional[WriteQuiescenceEvidence]: ...


class UnsupportedWriteQuiescenceVerifier:
    def verify(self, scope, receipt):
        return None
