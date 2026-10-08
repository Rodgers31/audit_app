"""Bounded async orchestration with all synchronous database work off-loop."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import logging
import time
from uuid import uuid4

from ..contracts import (
    CapabilitySet, DefinitiveAbsenceProof, OperationPlan, OperationResult, ReconciliationResult,
    ResolvedPostPayload, ValidationResult, canonical_hash,
)
from .logging import event
from .policy import bounded_json, retry_decision, validate_plan
from .repository import Claim, GateRejected, LeaseLost, QueueRepository
from .materials import CredentialLoadRequest

logger = logging.getLogger("social.worker")


class SocialWorker:
    """No adapters are registered by default; tests must explicitly supply fakes."""
    def __init__(self, repository: QueueRepository, *, adapters=None,
                 credential_loader=None, media_access=None):
        self.repository = repository
        self.config = repository.config
        self.adapters = dict(adapters or {})
        self.credential_loader = credential_loader
        self.media_access = media_access
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="social-db")
        self.stop_event = asyncio.Event()
        self.tasks = set()
        self._last_heartbeat = 0.0
        self._last_success = False

    async def db(self, function, *args, **kwargs):
        return await asyncio.get_running_loop().run_in_executor(self.executor, partial(function, *args, **kwargs))

    def stop(self):
        self.stop_event.set()

    async def close(self):
        self.stop()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.executor.shutdown(wait=True)

    async def run(self, *, once=False):
        await self.db(self.repository.validate_schema)
        try:
            while not self.stop_event.is_set():
                try:
                    await self.db(self.repository.recover_expired)
                    free = self.config.external_slots-len(self.tasks)
                    claims = await self.db(self.repository.claim_due, free) if free else []
                    for claim in claims:
                        task = asyncio.create_task(self.process(claim))
                        self.tasks.add(task)
                        task.add_done_callback(self.tasks.discard)
                    active = bool(self.tasks or claims)
                    interval = self.config.active_heartbeat_seconds if active else self.config.idle_heartbeat_seconds
                    if time.monotonic()-self._last_heartbeat >= interval:
                        await self.db(self.repository.heartbeat, state="active" if active else "idle",
                                      active_claims=len(self.tasks), scanned=True,
                                      success=self._last_success)
                        self._last_success = False
                        self._last_heartbeat = time.monotonic()
                    if once:
                        if self.tasks:
                            await asyncio.gather(*self.tasks, return_exceptions=False)
                        break
                    wait = self.config.active_scan_seconds if active else self.config.idle_scan_seconds
                    wait = await self.db(self.repository.next_due_delay, wait)
                    try:
                        await asyncio.wait_for(self.stop_event.wait(), timeout=wait)
                    except asyncio.TimeoutError:
                        pass
                except asyncio.CancelledError:
                    raise
                except Exception:
                    # Database failures never become adapter calls or fake health.
                    event(logger, "worker_scan_failed", worker_id=self.repository.worker_id,
                          error_code="DATABASE_UNAVAILABLE", outcome="unavailable")
                    try:
                        await asyncio.wait_for(self.stop_event.wait(), timeout=self.config.idle_scan_seconds)
                    except asyncio.TimeoutError:
                        pass
                    if once:
                        raise
            if self.tasks:
                await asyncio.gather(*self.tasks, return_exceptions=True)
        finally:
            try:
                await self.db(self.repository.heartbeat, state="stopped", active_claims=0)
            except Exception:
                event(logger, "worker_heartbeat_failed", worker_id=self.repository.worker_id,
                      error_code="DATABASE_UNAVAILABLE", outcome="unavailable")

    async def _renew(self, claim, completed):
        while not completed.is_set():
            try:
                await asyncio.wait_for(completed.wait(), timeout=self.config.renewal_seconds)
            except asyncio.TimeoutError:
                try:
                    if not await self.db(self.repository.renew, claim):
                        event(logger, "lease_lost", target_id=claim.target_id,
                              lease_epoch=claim.epoch, outcome="reconciliation_required")
                        return
                except Exception:
                    event(logger, "lease_renewal_failed", target_id=claim.target_id,
                          lease_epoch=claim.epoch, error_code="DATABASE_UNAVAILABLE",
                          outcome="reconciliation_required")
                    return

    async def process(self, claim: Claim):
        done = asyncio.Event()
        renewal = asyncio.create_task(self._renew(claim, done))
        intent = None
        started = time.monotonic()
        try:
            snapshot = await self.db(self.repository.load, claim)
            payload = ResolvedPostPayload.model_validate(snapshot["resolved_payload"])
            bounded_json(snapshot["checkpoint"])
            adapter = self.adapters.get((payload.platform, payload.api_product))
            if adapter is None:
                state = "outcome_unknown" if claim.previous_state == "reconciling" else "blocked"
                await self.db(self.repository.abandon, claim, state=state, code="ADAPTER_NOT_AVAILABLE")
                return
            reconciling = claim.previous_state == "reconciling"
            if reconciling:
                plan = OperationPlan(operation_id=uuid4(), operation="reconcile",
                                     publication_capable=False, safe_replay_class="read_only",
                                     checkpoint=snapshot["checkpoint"])
            else:
                capabilities = CapabilitySet.model_validate(adapter.capabilities(snapshot))
                if not capabilities.adapter_available:
                    await self.db(self.repository.abandon, claim, state="blocked", code="ADAPTER_NOT_AVAILABLE")
                    return
                if claim.previous_state != "processing":
                    validation = ValidationResult.model_validate(adapter.validate(payload, capabilities))
                    if not validation.valid or validation.errors or any(not target.valid or target.errors for target in validation.targets):
                        await self.db(self.repository.abandon, claim, state="failed", code="TARGET_VALIDATION_FAILED")
                        return
                plan = OperationPlan.model_validate(adapter.next_operation(payload, snapshot["checkpoint"]))
            validate_plan(plan, snapshot["checkpoint"])
            admission_check = getattr(adapter, "validate_mutation_admission", None)
            if plan.safe_replay_class != "read_only" and callable(admission_check):
                admission = ValidationResult.model_validate(admission_check(payload, snapshot))
                if not admission.valid or admission.errors or any(not target.valid or target.errors for target in admission.targets):
                    await self.db(self.repository.abandon, claim, state="blocked", code="ACCOUNT_INELIGIBLE")
                    return
            if not 0 < plan.timeout_seconds < self.config.lease_seconds:
                raise ValueError("Adapter timeout must be shorter than claim lease")
            intent = await self.db(
                self.repository.begin_operation, claim, operation_id=plan.operation_id,
                operation=plan.operation, publication_capable=plan.publication_capable,
                mutating=plan.safe_replay_class != "read_only", safe_replay_class=plan.safe_replay_class,
                request_fingerprint=canonical_hash({"payload_hash": payload.content_hash,
                                                    "operation": plan.operation,
                                                    "checkpoint": plan.checkpoint}),
                checkpoint_input=plan.checkpoint, estimated_cost_microusd=plan.estimated_cost_microusd,
                expected_capability_hash=canonical_hash(snapshot["capability_snapshot"]),
            )
            if intent is None:
                return
            # Bind ephemeral material to this committed intent and admission
            # snapshot, including authenticated reads after restart.
            credential = await self.credential_loader(CredentialLoadRequest(
                claim, payload, plan.operation_id, snapshot['admitted_credential_id'],
                snapshot['admitted_credential_version'], plan.safe_replay_class != 'read_only',
            )) if self.credential_loader else None
            media_access = self.media_access.for_payload(payload) if self.media_access else None
            try:
                if reconciling:
                    remote = await asyncio.wait_for(
                        adapter.reconcile(payload, snapshot["checkpoint"], snapshot["last_attempt"], credential, media_access),
                        timeout=plan.timeout_seconds)
                else:
                    remote = await asyncio.wait_for(adapter.execute(payload, plan, credential, media_access),
                                                    timeout=plan.timeout_seconds)
            except Exception:
                # Adapter exceptions cannot establish that a mutation was unsent.
                result = OperationResult(outcome="ambiguous", error_code="ADAPTER_OPERATION_UNCERTAIN")
                state = "reconciling" if plan.safe_replay_class != "read_only" else (
                    "reconciling" if reconciling else "processing")
                await self._save(claim, intent, snapshot, result, state=state,
                                 next_action="reconcile" if state == "reconciling" else "poll",
                                 delay=30, duration_ms=int((time.monotonic()-started)*1000))
                return
            # Persist outside the exception classifier: DB failure after acceptance
            # must retain the original durable intent, never invent an unsent result.
            if reconciling:
                try:
                    reconciliation = ReconciliationResult.model_validate(remote)
                except (ValueError, TypeError):
                    # Invalid/false absence proof is an unknown outcome, rather
                    # than an incomplete read intent or permission to resubmit.
                    result = OperationResult(outcome="ambiguous", error_code="INVALID_RECONCILIATION_PROOF")
                    await self._save(claim, intent, snapshot, result, state="outcome_unknown",
                                     duration_ms=int((time.monotonic()-started)*1000))
                    return
                await self._reconciliation(claim, intent, snapshot, reconciliation, started)
            else:
                result = OperationResult.model_validate(remote)
                await self._result(claim, intent, snapshot, plan, result, started)
        except LeaseLost:
            event(logger, "claim_fenced", target_id=claim.target_id, lease_epoch=claim.epoch,
                  outcome="lease_lost")
        except (ValueError, TypeError):
            if intent is None:
                try:
                    await self.db(self.repository.abandon, claim,
                                  state="outcome_unknown" if claim.previous_state in ("processing", "reconciling") else "failed",
                                  code="MALFORMED_CHECKPOINT_OR_ADAPTER_CONTRACT")
                except LeaseLost:
                    pass
            else:
                event(logger, "operation_contract_invalid", target_id=claim.target_id,
                      operation_id=intent.operation_id, error_code="ADAPTER_CONTRACT_INVALID",
                      outcome="reconciliation_required")
        except Exception:
            # A receipt persistence failure is loud. The durable intent survives
            # and expired-lease recovery reconciles; there is no local resubmit.
            event(logger, "operation_persistence_failed", target_id=claim.target_id,
                  operation_id=intent.operation_id if intent else None,
                  lease_epoch=claim.epoch, error_code="DATABASE_UNAVAILABLE",
                  outcome="reconciliation_required" if intent else "not_dispatched")
        finally:
            done.set()
            await renewal

    @staticmethod
    def _confirmed(result):
        return (result.outcome == "confirmed_success" and result.visibility_state == "public"
                and bool(result.primary_remote_id and result.primary_remote_id.strip())
                and bool(result.confirmation_kind and result.confirmation_kind.strip()))

    async def _result(self, claim, intent, snapshot, plan, result, started):
        bounded_json(result.checkpoint)
        bounded_json(result.remote_refs)
        bounded_json(result.receipt)
        delay, action, state = None, None, "failed"
        if result.outcome == "confirmed_success":
            if self._confirmed(result) and (plan.publication_capable or plan.operation == "poll"):
                state = "published"
            elif plan.publication_capable or plan.operation == "poll":
                state, action, delay = "processing", "poll", self._delay(result.next_action_at, snapshot, 30)
            else:
                state, action, delay = "queued", "continue", 0
        elif result.outcome == "processing":
            state, action, delay = "processing", "poll", self._delay(result.next_action_at, snapshot, 30)
        elif result.outcome == "ambiguous":
            state, action, delay = "reconciling", "reconcile", 30
        else:
            policy = await self.db(self.repository.retry_policy, claim, result)
            state = {"retry": "retry_wait", "block": "blocked", "fail": "failed", "reconcile": "reconciling"}[policy.action]
            result = result.model_copy(update={"error_code": policy.reason})
            if policy.action == "retry":
                action, delay = "publish", self._delay(policy.next_action_at, snapshot, 30)
            elif policy.action == "reconcile":
                action, delay = "reconcile", 30
        await self._save(claim, intent, snapshot, result, state=state, next_action=action,
                         delay=delay, duration_ms=int((time.monotonic()-started)*1000))

    async def _reconciliation(self, claim, intent, snapshot, reconciliation, started):
        bounded_json(reconciliation.evidence)
        result = reconciliation.result or OperationResult(outcome="ambiguous", error_code="RECONCILIATION_REQUIRED")
        absence_proof = None
        if reconciliation.absence_proof is not None:
            try:
                absence_proof = DefinitiveAbsenceProof.model_validate(reconciliation.absence_proof.model_dump(mode="json"))
            except (ValueError, TypeError, AttributeError):
                pass
        original = snapshot["last_attempt"]
        valid_absence = bool(absence_proof and original and
            (original["receipt"] or {}).get("intent", {}).get("mutating") is True and
            absence_proof.verified is True and absence_proof.coverage_complete is True and
            str(absence_proof.account_id) == str(snapshot["account_id"]) and
            str(absence_proof.operation_id) == str(original["operation_id"]))
        if reconciliation.outcome == "confirmed_published" and self._confirmed(result):
            state, action, delay = "published", None, None
        elif reconciliation.outcome == "definitively_unpublished":
            # Generic evidence can describe failed/incomplete lookup. Resending
            # needs positive typed proof bound to this original mutation/account.
            if not valid_absence:
                state, action, delay = "outcome_unknown", None, None
            else:
                safe = OperationResult(outcome="definite_failure", error_code="NOT_SENT", retry_safe=True,
                                       next_action_at=reconciliation.next_action_at)
                policy = await self.db(self.repository.retry_policy, claim, safe)
                state = "retry_wait" if policy.action == "retry" else "blocked"
                action = "publish" if policy.action == "retry" else None
                delay = self._delay(policy.next_action_at, snapshot, 30) if action else None
                result = safe.model_copy(update={"error_code": policy.reason})
        elif reconciliation.outcome == "still_processing":
            state, action = "processing", "poll"
            delay = self._delay(reconciliation.next_action_at, snapshot, 30)
        else:
            state, action, delay = "outcome_unknown", None, None
        await self._save(claim, intent, snapshot, result, state=state, next_action=action,
                         delay=delay, duration_ms=int((time.monotonic()-started)*1000),
                         extra_receipt={"reconciliation_evidence": reconciliation.evidence,
                                        "absence_proof": absence_proof.model_dump(mode="json") if valid_absence else None})

    @staticmethod
    def _delay(next_at, snapshot, default):
        if next_at is None:
            return default
        if next_at.tzinfo is None:
            raise ValueError("Provider next action time must include a timezone")
        return max(default, (next_at-snapshot["database_now"]).total_seconds())

    async def _save(self, claim, intent, snapshot, result, *, state, next_action=None,
                    delay=None, duration_ms=0, extra_receipt=None):
        # Store compact typed evidence, never arbitrary raw provider receipts.
        receipt = {"primary_remote_id": result.primary_remote_id,
                   "remote_refs": result.remote_refs, "checkpoint": result.checkpoint,
                   "visibility_state": result.visibility_state,
                   "confirmation_kind": result.confirmation_kind, "retry_safe": result.retry_safe, **(extra_receipt or {})}
        current = await self.db(self.repository.finish, claim, intent, state=state,
            outcome=result.outcome, checkpoint={**snapshot["checkpoint"], **result.checkpoint},
            remote_refs={**snapshot["remote_refs"], **result.remote_refs},
            remote_id=result.primary_remote_id, remote_url=result.remote_url,
            visibility_state=result.visibility_state, confirmation_kind=result.confirmation_kind,
            error_code=result.error_code, safe_error_message=result.safe_error_message,
            provider_request_id=result.provider_request_id, http_status=result.http_status,
            provider_code=result.provider_code, next_action=next_action, delay=delay,
            receipt=receipt, duration_ms=duration_ms)
        self._last_success = current
        event(logger, "operation_finished", worker_id=self.repository.worker_id,
              target_id=claim.target_id, account_id=claim.account_id,
              publication_id=claim.publication_id, operation_id=intent.operation_id,
              lease_epoch=claim.epoch, attempt_sequence=intent.sequence,
              duration_ms=duration_ms, outcome=state if current else "late_evidence",
              error_code=result.error_code)
