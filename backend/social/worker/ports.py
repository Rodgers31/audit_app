"""Adapter operation boundaries; domain models are the single shared contract."""
from __future__ import annotations

from typing import Any, Mapping, Protocol

from ..contracts import (
    CapabilitySet, OperationPlan, OperationResult, ReconciliationResult,
    ResolvedPostPayload, ValidationResult,
)
from .materials import InspectedMediaAccess, WorkerCredentialMaterial


class SocialPlatformAdapter(Protocol):
    def capabilities(self, account: Mapping[str, Any]) -> CapabilitySet: ...
    def validate(self, payload: ResolvedPostPayload, capabilities: CapabilitySet) -> ValidationResult: ...
    def next_operation(self, payload: ResolvedPostPayload, checkpoint: dict) -> OperationPlan: ...
    async def execute(self, payload: ResolvedPostPayload, operation: OperationPlan, credential: WorkerCredentialMaterial | None, media_access: InspectedMediaAccess | None) -> OperationResult: ...
    async def reconcile(self, payload: ResolvedPostPayload, checkpoint: dict, attempt: Mapping[str, Any] | None, credential: WorkerCredentialMaterial | None, media_access: InspectedMediaAccess | None) -> ReconciliationResult: ...
