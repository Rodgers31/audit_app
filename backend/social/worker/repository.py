"""Short PostgreSQL transactions, minimal claims and token/epoch fencing.

Every transaction touching admission plus delivery rows locks controls, account,
publication, then target. Claim-only transactions touch targets and nothing else.
No Connection or Session escapes a method or spans an external await.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .config import WorkerConfig
from ..contracts import CapabilitySet, DefinitiveAbsenceProof, OperationPlan, PostDocument, ResolvedPostPayload, canonical_hash
from .policy import bounded_json, retry_decision, validate_plan
from ..validation import validate_document

ACTIONABLE_STATES = ("queued", "retry_wait", "processing", "reconciling")
READ_BUDGET_LIMIT = 100
READ_REQUEST_WINDOW_SECONDS = 86400
REQUIRED_TABLES = (
    "social_controls", "social_accounts", "social_posts", "social_post_revisions",
    "social_publications", "social_post_targets", "social_publish_attempts",
    "social_audit_events", "social_worker_heartbeats",
)


@dataclass(frozen=True)
class Claim:
    target_id: str
    account_id: str
    publication_id: str
    token: str
    epoch: int
    previous_state: str


@dataclass(frozen=True)
class Intent:
    operation_id: str
    sequence: int
    dispatch_started_at: datetime | None


class LeaseLost(Exception):
    """The current durable claim belongs to another execution epoch."""


class GateRejected(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _json(value):
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":"))


class QueueRepository:
    def __init__(self, engine: Engine, config: WorkerConfig, worker_id: UUID):
        self.engine, self.config, self.worker_id = engine, config, str(worker_id)

    def validate_schema(self):
        with self.engine.connect() as conn:
            for name in REQUIRED_TABLES:
                if conn.execute(text("SELECT to_regclass(:name)"), {"name": name}).scalar() is None:
                    raise GateRejected("SOCIAL_SCHEMA_UNAVAILABLE")
            conn.execute(text("SELECT id FROM social_controls LIMIT 1"))

    def claim_due(self, limit: int = 1) -> list[Claim]:
        if type(limit) is not int or not 1 <= limit <= self.config.external_slots:
            raise ValueError("Claim count exceeds free bounded execution slots")
        with self.engine.begin() as conn:
            rows = conn.execute(text("""
                WITH due AS (
                    SELECT id, state AS previous_state
                    FROM social_post_targets
                    WHERE state IN ('queued','retry_wait','processing','reconciling')
                      AND next_action_at <= now() AND lease_token IS NULL
                    ORDER BY next_action_at, id
                    FOR UPDATE SKIP LOCKED LIMIT :limit
                )
                UPDATE social_post_targets AS target
                SET lease_owner=:owner, lease_token=gen_random_uuid(),
                    lease_epoch=target.lease_epoch+1,
                    lease_expires_at=now()+make_interval(secs => :lease_seconds),
                    state=CASE WHEN due.previous_state IN ('queued','retry_wait')
                               THEN 'claimed' ELSE target.state END,
                    updated_at=now()
                FROM due WHERE target.id=due.id
                RETURNING target.id, target.account_id, target.publication_id,
                          target.lease_epoch, target.lease_token, due.previous_state
            """), {"limit": limit, "owner": self.worker_id,
                    "lease_seconds": self.config.lease_seconds}).mappings().all()
            claims = [Claim(str(r["id"]), str(r["account_id"]), str(r["publication_id"]),
                            str(r["lease_token"]), r["lease_epoch"], r["previous_state"]) for r in rows]
            for claim in claims:
                self._audit(conn, claim, "target_claimed", claim.previous_state,
                            "claimed" if claim.previous_state in ("queued", "retry_wait")
                            else claim.previous_state,
                            {"account_id": claim.account_id, "publication_id": claim.publication_id,
                             "lease_epoch": claim.epoch}, related_fks=False)
            return claims

    def next_due_delay(self, ceiling: float) -> float:
        with self.engine.connect() as conn:
            delay = conn.execute(text("""
                SELECT EXTRACT(EPOCH FROM next_action_at-now())
                FROM social_post_targets
                WHERE state IN ('queued','retry_wait','processing','reconciling')
                  AND lease_token IS NULL AND next_action_at > now()
                ORDER BY next_action_at, id LIMIT 1
            """)).scalar()
        return min(ceiling, max(0.01, float(delay))) if delay is not None else ceiling

    def load(self, claim: Claim) -> dict:
        with self.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT now() AS database_now, t.*, a.platform, a.api_product, a.connection_state,
                       a.publishing_enabled AS account_enabled, a.capability_snapshot,
                       a.granted_scopes, p.post_id, p.revision_id, p.approved_hash,
                       p.approved_at, p.authorization_kind, p.approved_by,
                       p.cancel_requested_at, p.revoked_at, p.start_deadline,
                       p.retry_deadline, p.content_valid_until, p.dispatch_requested_at,
                       r.content_hash AS revision_hash
                FROM social_post_targets t
                JOIN social_accounts a ON a.id=t.account_id
                JOIN social_publications p ON p.id=t.publication_id
                JOIN social_post_revisions r ON r.id=p.revision_id
                WHERE t.id=CAST(:id AS uuid)
                  AND t.lease_token=CAST(:token AS uuid) AND t.lease_epoch=:epoch
                  AND t.lease_expires_at > now()
            """), self._params(claim)).mappings().first()
            if row is None:
                raise LeaseLost()
            data = dict(row)
            attempt = conn.execute(text("""
                SELECT id, operation_id, operation, outcome, receipt,
                       dispatch_started_at, sequence
                FROM social_publish_attempts WHERE target_id=CAST(:id AS uuid)
                ORDER BY CASE WHEN :reconciling AND receipt->'intent'->>'mutating'='true'
                              THEN 0 ELSE 1 END, sequence DESC LIMIT 1
            """), {**self._params(claim), "reconciling": claim.previous_state == "reconciling"}).mappings().first()
            data["last_attempt"] = dict(attempt) if attempt else None
            return data

    def _locked(self, conn, claim: Claim):
        controls = conn.execute(text("SELECT * FROM social_controls WHERE id=1 FOR UPDATE")).mappings().first()
        account = conn.execute(text("SELECT * FROM social_accounts WHERE id=CAST(:account AS uuid) FOR UPDATE"),
                               self._params(claim)).mappings().first()
        publication = conn.execute(text("SELECT * FROM social_publications WHERE id=CAST(:publication AS uuid) FOR UPDATE"),
                                   self._params(claim)).mappings().first()
        target = conn.execute(text("SELECT * FROM social_post_targets WHERE id=CAST(:id AS uuid) FOR UPDATE"),
                              self._params(claim)).mappings().first()
        return controls, account, publication, target

    def _current(self, conn, claim, target):
        if (target is None or str(target["lease_token"]) != claim.token or target["lease_epoch"] != claim.epoch
                or str(target["account_id"]) != claim.account_id or str(target["publication_id"]) != claim.publication_id):
            raise LeaseLost()
        now = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
        if target["lease_expires_at"] is None or target["lease_expires_at"] <= now:
            raise LeaseLost()
        return now

    def begin_operation(self, claim: Claim, *, operation_id: UUID, operation: str,
                        publication_capable: bool, mutating: bool, safe_replay_class: str,
                        request_fingerprint: str, checkpoint_input: dict,
                        estimated_cost_microusd: int = 0, expected_capability_hash: str | None = None) -> Intent | None:
        """Commit dispatch permission and intent before handing control to an adapter."""
        plan = OperationPlan(operation_id=operation_id, operation=operation,
                             publication_capable=publication_capable, safe_replay_class=safe_replay_class,
                             checkpoint=checkpoint_input, estimated_cost_microusd=estimated_cost_microusd)
        validate_plan(plan, checkpoint_input)
        if type(mutating) is not bool or mutating != (safe_replay_class != "read_only"):
            raise ValueError("Mutation classification must match the operation contract")
        with self.engine.begin() as conn:
            controls, account, pub, target = self._locked(conn, claim)
            now = self._current(conn, claim, target)
            pending = conn.execute(text("SELECT operation_id FROM social_publish_attempts WHERE target_id=CAST(:id AS uuid) AND lease_epoch=:epoch AND completed_at IS NULL LIMIT 1"), self._params(claim)).scalar()
            if pending is not None:
                raise GateRejected("OPERATION_ALREADY_STARTED")
            if target["checkpoint"] != checkpoint_input:
                raise GateRejected("CHECKPOINT_CONFLICT")
            if estimated_cost_microusd:
                # Paid reads also need a reviewed accounting reservation. Pause
                # permits status reads, but never implicitly authorizes spending.
                self._transition(conn, claim, target, "blocked", "BUDGET_RESERVATION_UNAVAILABLE")
                return None
            if not mutating:
                resume_at = self._read_budget_resume_at(conn, claim, now)
                if resume_at is not None:
                    # A budget is a temporary admission restriction, not evidence
                    # about an accepted mutation. Keep its checkpoint and hold,
                    # and reserve no new operation until a read leaves the window.
                    waiting_state = (claim.previous_state if claim.previous_state in ("processing", "reconciling")
                                     else "reconciling" if operation == "reconcile" else "processing")
                    if waiting_state == "reconciling":
                        self._hold_account(conn, claim)
                    self._transition(conn, claim, target, waiting_state, "STATUS_CHECK_LIMIT",
                                     delay=max(0.01, (resume_at-now).total_seconds()),
                                     next_action="reconcile" if waiting_state == "reconciling" else "poll")
                    return None
            if mutating:
                if expected_capability_hash is not None and canonical_hash(account["capability_snapshot"]) != expected_capability_hash:
                    self._transition(conn, claim, target, "blocked", "CAPABILITY_CHANGED")
                    return None
                code = self._gate(conn, controls, account, pub, target, now, publication_capable)
                if code:
                    if code in ("PUBLISHING_PAUSED", "PLATFORM_PAUSED"):
                        # Keep the exact checkpoint; a resumed control may admit
                        # this same authorized operation, subject to fresh deadlines.
                        waiting_state = claim.previous_state if claim.previous_state == "processing" else "queued"
                        self._transition(conn, claim, target, waiting_state, code, delay=30,
                                         next_action=target["next_action"] or "continue")
                    else:
                        self._transition(conn, claim, target, "cancelled" if code == "CANCELLED" else "blocked", code)
                    return None
                admission = account["publish_lease_token"]
                if admission and (str(admission) != claim.token or str(account["publish_lease_target_id"]) != claim.target_id) and account["publish_lease_expires_at"] <= now:
                    # Expiry does not prove an earlier HTTP request has stopped.
                    # Recovery must inspect its durable intent before account reuse.
                    previous_id = str(account["publish_lease_target_id"])
                    conn.execute(text("UPDATE social_accounts SET hold_reason=:hold,updated_at=now() WHERE id=CAST(:account AS uuid) AND hold_reason IS NULL"),
                                 {**self._params(claim), "hold": "RECONCILIATION_REQUIRED:"+previous_id})
                    self._transition(conn, claim, target, "blocked", "ACCOUNT_RECONCILIATION_REQUIRED")
                    return None
                if admission and account["publish_lease_expires_at"] > now and (
                    str(admission) != claim.token or str(account["publish_lease_target_id"]) != claim.target_id
                ):
                    self._transition(conn, claim, target, "queued", "ACCOUNT_BUSY", delay=5,
                                     next_action=target["next_action"] or "publish")
                    return None
                conn.execute(text("""
                    UPDATE social_accounts SET publish_lease_target_id=CAST(:id AS uuid),
                        publish_lease_token=CAST(:token AS uuid),
                        publish_lease_expires_at=clock_timestamp()+make_interval(secs => :lease_seconds),
                        updated_at=now() WHERE id=CAST(:account AS uuid)
                """), {**self._params(claim), "lease_seconds": self.config.lease_seconds})
            sequence = conn.execute(text("SELECT COALESCE(MAX(sequence),0)+1 FROM social_publish_attempts WHERE target_id=CAST(:id AS uuid)"),
                                    self._params(claim)).scalar_one()
            receipt = {"intent": {"publication_capable": publication_capable,
                                   "mutating": mutating, "safe_replay_class": safe_replay_class}}
            conn.execute(text("""
                INSERT INTO social_publish_attempts
                    (id,target_id,sequence,operation_id,operation,request_fingerprint,
                     lease_epoch,dispatch_started_at,outcome,receipt,estimated_cost_microusd,
                     cost_reservation_state,created_at)
                VALUES (CAST(:attempt AS uuid),CAST(:id AS uuid),:sequence,CAST(:operation_id AS uuid),
                        :operation,:fingerprint,:epoch,
                        CASE WHEN :public THEN clock_timestamp() ELSE NULL END,'intent',CAST(:receipt AS jsonb),
                        :cost,'not_required',clock_timestamp())
            """), {**self._params(claim), "attempt": str(uuid4()), "sequence": sequence,
                    "operation_id": str(operation_id), "operation": operation,
                    "fingerprint": request_fingerprint, "public": publication_capable,
                    "receipt": _json(receipt), "cost": estimated_cost_microusd})
            conn.execute(text("""
                UPDATE social_post_targets SET state=CASE WHEN :public THEN 'dispatching' ELSE state END,
                    submit_count=submit_count+CASE WHEN :public THEN 1 ELSE 0 END,
                    updated_at=now() WHERE id=CAST(:id AS uuid)
            """), {**self._params(claim), "public": publication_capable})
            self._audit(conn, claim, "operation_intent", target["state"],
                        "dispatching" if publication_capable else target["state"],
                        {"operation_id": str(operation_id), "operation": operation,
                         "lease_epoch": claim.epoch, "sequence": sequence})
            return Intent(str(operation_id), sequence, now if publication_capable else None)

    def _gate(self, conn, controls, account, pub, target, now, public):
        if pub is None or account is None or controls is None:
            return "SOCIAL_SCHEMA_UNAVAILABLE"
        if pub["cancel_requested_at"] or pub["revoked_at"]:
            return "CANCELLED"
        if not controls["publishing_enabled"]:
            return "PUBLISHING_PAUSED"
        platform_control = (controls["platform_controls"] or {}).get(account["platform"], {})
        if platform_control.get("publishing_enabled") is False:
            return "PLATFORM_PAUSED"
        if not account["publishing_enabled"] or account["connection_state"] != "connected" or account["hold_reason"]:
            return "ACCOUNT_UNAVAILABLE"
        if not pub["approved_at"] or (pub["authorization_kind"] == "human" and not pub["approved_by"]):
            return "AUTHORIZATION_INVALID"
        revision = conn.execute(text("SELECT post_id,document,evidence_snapshot,content_hash FROM social_post_revisions WHERE id=CAST(:revision AS uuid)"),
                                {"revision": str(pub["revision_id"])}).mappings().first()
        if not revision or str(revision["post_id"]) != str(pub["post_id"]):
            return "AUTHORIZATION_OWNERSHIP_MISMATCH"
        actual_revision_hash = canonical_hash({"document": revision["document"], "evidence_snapshot": revision["evidence_snapshot"]})
        if revision["content_hash"] != pub["approved_hash"] or actual_revision_hash != pub["approved_hash"]:
            return "AUTHORIZATION_HASH_MISMATCH"
        try:
            payload = ResolvedPostPayload.model_validate(target["resolved_payload"])
            capability = CapabilitySet.model_validate(account["capability_snapshot"])
            bounded_json(target["checkpoint"])
        except (ValueError, TypeError):
            return "TARGET_DATA_INVALID"
        if str(payload.account_id) != str(account["id"]) or payload.platform != account["platform"] or payload.api_product != account["api_product"] or payload.external_account_id != account["external_account_id"]:
            return "PAYLOAD_ACCOUNT_MISMATCH"
        if canonical_hash(payload.model_dump(mode="json", exclude={"content_hash"})) != payload.content_hash:
            return "PAYLOAD_HASH_MISMATCH"
        if target["payload_hash"] != payload.content_hash:
            return "PAYLOAD_HASH_MISMATCH"
        if not capability.eligible or not capability.adapter_available:
            return "ACCOUNT_INELIGIBLE"
        if payload.format not in capability.supported_formats:
            return "UNSUPPORTED_FORMAT"
        if not set(capability.required_scopes).issubset(set(account["granted_scopes"])):
            return "PERMISSION_DENIED"
        if capability.feature_states.get("publishing") != "supported":
            return "CAPABILITY_UNAVAILABLE"
        if capability.price_class != "free":
            return "BUDGET_RESERVATION_UNAVAILABLE"
        if target["capability_version"] != capability.rules_version or payload.capability_version != capability.rules_version:
            return "CAPABILITY_VERSION_CHANGED"
        try:
            document = PostDocument.model_validate(revision["document"])
            selected = tuple(t for t in document.targets if str(t.account_id) == str(account["id"]))
            if len(selected) != 1:
                return "TARGET_NOT_AUTHORIZED"
            # Validate just this destination: another selected account's failure
            # cannot erase this target's independent authorized outcome.
            with Session(bind=conn, join_transaction_mode="rollback_only") as session:
                validation = validate_document(session, document.model_copy(update={"targets": selected}),
                                               revision["evidence_snapshot"], {account["platform"]})
            if not validation.valid or validation.targets[0].resolved_preview is None:
                return "TARGET_VALIDATION_FAILED"
            if validation.targets[0].resolved_preview.model_dump(mode="json") != payload.model_dump(mode="json"):
                return "PAYLOAD_REVISION_MISMATCH"
        except (ValueError, TypeError):
            return "TARGET_DATA_INVALID"
        for asset in payload.assets:
            row = conn.execute(text("SELECT state,deleted_at,sha256,mime_type,byte_size FROM social_media_assets WHERE id=CAST(:asset AS uuid)"), {"asset": str(asset.asset_id)}).mappings().first()
            if not row or row["state"] != "ready" or row["deleted_at"] or row["sha256"] != asset.sha256 or row["mime_type"] != asset.mime_type or row["byte_size"] != asset.byte_size:
                return "MEDIA_UNAVAILABLE"
            if asset.caption_asset_id:
                caption = conn.execute(text("SELECT state,deleted_at,sha256 FROM social_media_assets WHERE id=CAST(:asset AS uuid)"), {"asset": str(asset.caption_asset_id)}).mappings().first()
                if not caption or caption["state"] != "ready" or caption["deleted_at"] or caption["sha256"] != asset.caption_sha256:
                    return "MEDIA_UNAVAILABLE"
        if pub["content_valid_until"] and pub["content_valid_until"] <= now:
            return "CONTENT_EXPIRED"
        if public:
            first = conn.execute(text("SELECT MIN(dispatch_started_at) FROM social_publish_attempts WHERE target_id=:id"), {"id": target["id"]}).scalar()
            if first and first+timedelta(seconds=self.config.retry_lifetime_seconds) <= now:
                return "RETRY_DEADLINE_EXCEEDED"
            if target["submit_count"] >= self.config.max_submissions:
                return "SUBMISSION_LIMIT"
            if target["submit_count"] == 0 and pub["start_deadline"] and pub["start_deadline"] <= now:
                return "START_DEADLINE_EXCEEDED"
            if target["submit_count"] and pub["retry_deadline"] and pub["retry_deadline"] <= now:
                return "RETRY_DEADLINE_EXCEEDED"
        return None

    def renew(self, claim: Claim) -> bool:
        with self.engine.begin() as conn:
            _, account, _, target = self._locked(conn, claim)
            try:
                self._current(conn, claim, target)
            except LeaseLost:
                return False
            conn.execute(text("UPDATE social_post_targets SET lease_expires_at=clock_timestamp()+make_interval(secs => :seconds) WHERE id=CAST(:id AS uuid)"),
                         {**self._params(claim), "seconds": self.config.lease_seconds})
            if account and str(account["publish_lease_token"]) == claim.token and str(account["publish_lease_target_id"]) == claim.target_id:
                conn.execute(text("UPDATE social_accounts SET publish_lease_expires_at=clock_timestamp()+make_interval(secs => :seconds) WHERE id=CAST(:account AS uuid)"),
                             {**self._params(claim), "seconds": self.config.lease_seconds})
            return True

    def finish(self, claim: Claim, intent: Intent, *, state: str, outcome: str,
               checkpoint: dict, remote_refs: dict, remote_id: str | None = None,
               remote_url: str | None = None, error_code: str | None = None,
               safe_error_message: str | None = None, visibility_state: str = "unknown",
               confirmation_kind: str | None = None, http_status: int | None = None,
               provider_code: str | None = None, delay: float | None = None,
               next_action: str | None = None, receipt: dict | None = None,
               duration_ms: int = 0, provider_request_id: str | None = None) -> bool:
        with self.engine.begin() as conn:
            _, _, _, target = self._locked(conn, claim)
            # Remote observations win over memory: even a late worker's evidence is
            # retained. Only current unexpired ownership can transition the target.
            completed = conn.execute(text("""
                UPDATE social_publish_attempts SET completed_at=now(), outcome=:outcome,
                    receipt=receipt || CAST(:receipt AS jsonb), duration_ms=:duration,
                    provider_request_id=:provider_request_id,http_status=:http_status,provider_code=:provider_code
                WHERE operation_id=CAST(:operation_id AS uuid) AND target_id=CAST(:id AS uuid)
                  AND lease_epoch=:epoch AND completed_at IS NULL
                RETURNING operation,dispatch_started_at,receipt
            """), {**self._params(claim), "operation_id": intent.operation_id,
                    "outcome": outcome, "receipt": _json(receipt or {}),
                    "duration": duration_ms, "provider_request_id": provider_request_id,
                    "http_status": http_status, "provider_code": provider_code}).mappings().first()
            if completed is None:
                return False
            try:
                self._current(conn, claim, target)
            except LeaseLost:
                self._audit(conn, claim, "late_operation_evidence", None, None,
                            {"operation_id": intent.operation_id, "outcome": outcome})
                return False
            valid_absence = self._absence_proof_matches(conn, claim, receipt) if completed["operation"] == "reconcile" else False
            if state == "retry_wait" and completed["operation"] == "reconcile" and not valid_absence:
                state, error_code, next_action, delay = "outcome_unknown", "INVALID_RECONCILIATION_PROOF", None, None
            publication_operation = (completed["dispatch_started_at"] is not None and
                                     completed["receipt"].get("intent", {}).get("publication_capable") is True)
            if state == "published" and not (outcome == "confirmed_success" and isinstance(remote_id, str) and remote_id.strip() and isinstance(confirmation_kind, str) and confirmation_kind.strip() and visibility_state == "public" and
                                              (publication_operation or completed["operation"] in ("poll", "reconcile"))):
                raise ValueError("Publication requires a publication/status operation and confirmed public identity/receipt")
            conn.execute(text("""
                UPDATE social_post_targets SET checkpoint=CAST(:checkpoint AS jsonb),
                    remote_refs=CAST(:refs AS jsonb),
                    primary_remote_id=COALESCE(:remote_id,primary_remote_id),
                    remote_url=COALESCE(:url,remote_url),
                    published_at=CASE WHEN :state='published' THEN now() ELSE published_at END,
                    visibility_state=:visibility,confirmation_kind=:confirmation,
                    safe_error_message=:message WHERE id=CAST(:id AS uuid)
            """), {**self._params(claim), "checkpoint": _json(checkpoint), "refs": _json(remote_refs),
                    "remote_id": remote_id, "url": remote_url, "state": state,
                    "message": safe_error_message, "visibility": visibility_state,
                    "confirmation": confirmation_kind})
            if state in ("reconciling", "outcome_unknown"):
                self._hold_account(conn, claim)
            elif state == "published" or (valid_absence and state in ("retry_wait", "blocked", "failed")):
                self._clear_hold(conn, claim)
            self._transition(conn, claim, target, state, error_code, delay, next_action)
            return True

    def abandon(self, claim: Claim, *, state: str, code: str):
        with self.engine.begin() as conn:
            _, _, _, target = self._locked(conn, claim)
            self._current(conn, claim, target)
            if state == "outcome_unknown":
                self._hold_account(conn, claim)
            self._transition(conn, claim, target, state, code)

    def _hold_account(self, conn, claim):
        conn.execute(text("UPDATE social_accounts SET hold_reason=:hold,updated_at=now() WHERE id=CAST(:account AS uuid) AND (hold_reason IS NULL OR hold_reason=:hold)"), {**self._params(claim), "hold": "RECONCILIATION_REQUIRED:"+claim.target_id})

    def _absence_proof_matches(self, conn, claim, receipt):
        try:
            proof = DefinitiveAbsenceProof.model_validate((receipt or {}).get("absence_proof"))
        except (ValueError, TypeError):
            return False
        original = conn.execute(text("""
            SELECT operation_id FROM social_publish_attempts WHERE target_id=CAST(:id AS uuid)
              AND receipt->'intent'->>'mutating'='true' ORDER BY sequence DESC LIMIT 1
        """), self._params(claim)).scalar()
        return (proof.verified is True and proof.coverage_complete is True and
                str(proof.account_id) == claim.account_id and str(proof.operation_id) == str(original))

    def _clear_hold(self, conn, claim):
        conn.execute(text("UPDATE social_accounts SET hold_reason=NULL,updated_at=now() WHERE id=CAST(:account AS uuid) AND hold_reason=:hold"), {**self._params(claim), "hold": "RECONCILIATION_REQUIRED:"+claim.target_id})

    def _transition(self, conn, claim, target, state, code=None, delay=None, next_action=None):
        conn.execute(text("""
            UPDATE social_post_targets SET state=:state, error_code=:code,
                next_action=:action,
                next_action_at=CASE WHEN :delay IS NULL THEN NULL ELSE clock_timestamp()+make_interval(secs => :delay) END,
                lease_owner=NULL,lease_token=NULL,lease_expires_at=NULL,updated_at=now()
            WHERE id=CAST(:id AS uuid)
        """), {**self._params(claim), "state": state, "code": code,
                "action": next_action, "delay": delay})
        conn.execute(text("""
            UPDATE social_accounts SET publish_lease_target_id=NULL,publish_lease_token=NULL,
                publish_lease_expires_at=NULL,updated_at=now()
            WHERE id=CAST(:account AS uuid) AND publish_lease_token=CAST(:token AS uuid)
              AND publish_lease_target_id=CAST(:id AS uuid)
        """), self._params(claim))
        self._audit(conn, claim, "target_transition", target["state"], state,
                    {"error_code": code, "lease_epoch": claim.epoch})

    def recover_expired(self) -> int:
        with self.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT id,account_id,publication_id,lease_token,lease_epoch,state
                FROM social_post_targets WHERE lease_expires_at<=now() AND lease_token IS NOT NULL
                ORDER BY lease_expires_at,id LIMIT :limit
            """), {"limit": self.config.maintenance_batch_size}).mappings().all()
        recovered = 0
        for row in rows:
            claim = Claim(str(row["id"]), str(row["account_id"]), str(row["publication_id"]),
                          str(row["lease_token"]), row["lease_epoch"], row["state"])
            with self.engine.begin() as conn:
                _, _, _, target = self._locked(conn, claim)
                now = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
                if target is None or str(target["lease_token"]) != claim.token or target["lease_epoch"] != claim.epoch or target["lease_expires_at"] > now:
                    continue
                attempt = conn.execute(text("""
                    SELECT dispatch_started_at,receipt,outcome FROM social_publish_attempts
                    WHERE target_id=CAST(:id AS uuid) ORDER BY sequence DESC LIMIT 1
                """), self._params(claim)).mappings().first()
                uncertain = bool(attempt and (attempt["dispatch_started_at"] is not None or
                                 (attempt["receipt"] or {}).get("intent", {}).get("safe_replay_class") == "requires_reconciliation"))
                if uncertain:
                    self._hold_account(conn, claim)
                state = "reconciling" if uncertain else (
                    target["state"] if target["state"] in ("processing", "reconciling") else "queued")
                self._transition(conn, claim, target, state, "LEASE_EXPIRED", 0,
                                 "reconcile" if state == "reconciling" else "poll" if state == "processing" else "publish")
                recovered += 1
        return recovered

    def retry_policy(self, claim, result):
        with self.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT now() AS database_now,t.submit_count,p.retry_deadline,p.content_valid_until,
                    COALESCE((SELECT MIN(dispatch_started_at) FROM social_publish_attempts
                              WHERE target_id=t.id),t.created_at) AS first_started_at
                FROM social_post_targets t JOIN social_publications p ON p.id=t.publication_id
                WHERE t.id=CAST(:id AS uuid)
            """), self._params(claim)).mappings().one()
        return retry_decision(result, now=row["database_now"], submit_count=row["submit_count"],
                              first_started_at=row["first_started_at"], retry_deadline=row["retry_deadline"],
                              content_valid_until=row["content_valid_until"],
                              max_submissions=self.config.max_submissions,
                              lifetime_seconds=self.config.retry_lifetime_seconds)

    def read_budget_exhausted(self, claim):
        with self.engine.connect() as conn:
            now = conn.execute(text("SELECT clock_timestamp()")).scalar_one()
            return self._read_budget_resume_at(conn, claim, now) is not None

    def _read_budget_resume_at(self, conn, claim, now):
        # The target/time index bounds the scan to one target's rolling window.
        # The 100th newest read determines when fewer than 100 remain, including
        # imported history with more than 100 reads. Intents count even if their
        # result was lost; mutation/upload history never consumes this budget.
        return conn.execute(text("""
            SELECT created_at+make_interval(secs => :seconds)
            FROM social_publish_attempts
            WHERE target_id=CAST(:id AS uuid) AND operation IN ('poll','reconcile')
              AND created_at > :now-make_interval(secs => :seconds)
            ORDER BY created_at DESC OFFSET :offset LIMIT 1
        """), {**self._params(claim), "now": now,
                "seconds": READ_REQUEST_WINDOW_SECONDS, "offset": READ_BUDGET_LIMIT-1}).scalar()

    def heartbeat(self, *, state: str, active_claims: int, scanned: bool = False,
                  success: bool = False, error_code: str | None = None):
        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO social_worker_heartbeats (worker_id,deployment_version,started_at,
                    heartbeat_at,last_scan_at,last_success_at,active_claims,state,last_error_code)
                VALUES (CAST(:worker AS uuid),:version,now(),now(),
                    CASE WHEN :scanned THEN now() ELSE NULL END,
                    CASE WHEN :success THEN now() ELSE NULL END,:active,:state,:error)
                ON CONFLICT (worker_id) DO UPDATE SET heartbeat_at=now(),
                    last_scan_at=CASE WHEN :scanned THEN now() ELSE social_worker_heartbeats.last_scan_at END,
                    last_success_at=CASE WHEN :success THEN now() ELSE social_worker_heartbeats.last_success_at END,
                    active_claims=:active,state=:state,last_error_code=:error
            """), {"worker": self.worker_id, "version": self.config.deployment_version,
                    "active": active_claims, "state": state, "error": error_code,
                    "scanned": scanned, "success": success})

    def _audit(self, conn, claim, action, previous, new, details=None, *, related_fks=True):
        conn.execute(text("""
            INSERT INTO social_audit_events (id,post_id,target_id,account_id,actor_kind,
                action,previous_state,new_state,details,request_id,created_at)
            VALUES (CAST(:audit AS uuid),
                CASE WHEN :related THEN (SELECT post_id FROM social_publications WHERE id=CAST(:publication AS uuid)) ELSE NULL END,
                CAST(:id AS uuid),CASE WHEN :related THEN CAST(:account AS uuid) ELSE NULL END,'worker',:action,:previous,:new,
                CAST(:details AS jsonb),:worker,now())
        """), {**self._params(claim), "audit": str(uuid4()), "action": action,
                "previous": previous, "new": new, "details": _json(details or {}),
                "worker": self.worker_id, "related": related_fks})

    @staticmethod
    def _params(claim):
        return {"id": claim.target_id, "account": claim.account_id,
                "publication": claim.publication_id, "token": claim.token, "epoch": claim.epoch}
