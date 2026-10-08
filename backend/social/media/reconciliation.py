"""Internal operator evidence port. Storage metadata never proves write quiescence.

A trusted implementation must establish that previously admitted browser and
server writes are drained or irrevocably fenced. The production default has no
such capability. This port intentionally has no browser route or Boolean override.
"""
from datetime import datetime
from typing import Annotated, Protocol
from uuid import UUID

from pydantic import Field

from ..contracts import Hash, PositiveVersion, StrictModel

Epoch = Annotated[int, Field(strict=True, ge=0)]


class WriteQuiescenceReceipt(StrictModel):
    receipt_id: UUID
    evidence_hash: Hash


class WriteQuiescenceScope(StrictModel):
    asset_id: UUID
    storage_provider: str
    bucket: str
    upload_version: PositiveVersion
    grant_epoch: Epoch
    grant_expires_at: datetime | None
    finalization_epoch: PositiveVersion | None


class WriteQuiescenceEvidence(StrictModel):
    scope: WriteQuiescenceScope
    receipt: WriteQuiescenceReceipt
    verified_at: datetime


class ReconcileUpload(StrictModel):
    expected_version: PositiveVersion
    expected_grant_epoch: Epoch
    expected_finalization_epoch: PositiveVersion | None
    receipt: WriteQuiescenceReceipt


class WriteQuiescenceVerifier(Protocol):
    def verify(self, scope: WriteQuiescenceScope, receipt: WriteQuiescenceReceipt) -> WriteQuiescenceEvidence | None: ...


class UnsupportedWriteQuiescenceVerifier:
    def verify(self, scope, receipt):
        return None
