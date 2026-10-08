"""Transactional manual commands. No external network or automatic approval."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy import func, select, text, true
from sqlalchemy.orm import Session

from .contracts import PostDocument, ResolvedPostPayload, canonical_hash
from .models import (SocialAccount, SocialAuditEvent, SocialCommandReceipt, SocialControls, SocialMediaAsset, SocialPost, SocialPostRevision, SocialPostTarget, SocialPublication, SocialPublishAttempt, SocialRevisionAsset, SocialWorkerHeartbeat)
from .telemetry import log_event
from .validation import all_asset_ids, capability_for, resolve_schedule, validate_document


class SocialError(Exception):
    def __init__(self, code, message, status=409, *, field_errors=(), target_errors=(), retryable=False):
        self.code, self.message, self.status = code, message, status
        self.field_errors, self.target_errors, self.retryable = field_errors, target_errors, retryable
        super().__init__(code)

    def detail(self, request_id):
        return {"code": self.code, "message": self.message, "field_errors": list(self.field_errors), "target_errors": list(self.target_errors), "retryable": self.retryable, "request_id": str(request_id)}


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso(value):
    return utc(value).isoformat().replace("+00:00", "Z") if value is not None else None


def require_positive_version(value):
    """Protect internal callers as well as the strict HTTP request schemas."""
    if type(value) is not int or value < 1:
        raise SocialError("INVALID_REQUEST", "Expected version must be a positive integer.", 422)


def document_json(document):
    value = document.model_dump(mode="json")
    for index, target in enumerate(document.targets):
        value["targets"][index]["overrides"] = target.overrides.model_dump(mode="json", exclude_unset=True)
    return value


SENSITIVE_CATEGORIES = frozenset({"debt_update", "budget_update", "audit_finding", "financial_claim", "correction", "allegation", "reputational_claim"})
INFLIGHT = frozenset({"dispatching", "processing", "reconciling", "outcome_unknown", "published"})


class SocialService:
    def __init__(self, db: Session, *, available_adapters=frozenset()):
        self.db = db
        from collections.abc import Mapping
        from types import MappingProxyType
        self.available_adapters = MappingProxyType(dict(available_adapters)) if isinstance(available_adapters, Mapping) else frozenset(available_adapters)
        self.actor = None
        self.request_id = None

    def now(self):
        clock = func.clock_timestamp() if self.db.bind.dialect.name == "postgresql" else func.now()
        return utc(self.db.scalar(select(clock)))

    def command(self, *, actor: UUID, route: str, key: UUID, body, request_id: UUID, action: Callable, status=200):
        """Receipt, mutation and audit share one transaction; PG lock serializes keys."""
        self.actor, self.request_id = actor, request_id
        request_hash = canonical_hash(body)
        with self.db.begin():
            if self.db.bind.dialect.name == "postgresql":
                lock_value = int(canonical_hash([str(actor), route, str(key)])[:16], 16)
                if lock_value >= 2**63:
                    lock_value -= 2**64
                self.db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_value})
            receipt = self.db.scalar(select(SocialCommandReceipt).where(SocialCommandReceipt.actor_key == str(actor), SocialCommandReceipt.route_key == route, SocialCommandReceipt.idempotency_key == key))
            if receipt:
                if receipt.request_hash != request_hash:
                    raise SocialError("IDEMPOTENCY_CONFLICT", "This command key was already used with different input.")
                return receipt.http_status, receipt.response
            result = action()
            self.db.flush()
            now = self.now()
            resource_id = result.get("id") or result.get("post_id")
            self.db.add(SocialCommandReceipt(actor_key=str(actor), route_key=route, idempotency_key=key, request_hash=request_hash, resource_id=UUID(resource_id) if resource_id else None, http_status=status, response=result, expires_at=now + timedelta(days=30)))
            self.db.flush()
        log_event("social.command_committed", request_id=request_id, post_id=resource_id, action=route, result="committed")
        return status, result

    def audit(self, action, *, post=None, target=None, previous=None, new=None, reason=None, details=None):
        self.db.add(SocialAuditEvent(post_id=post.id if post else None, target_id=target.id if target else None, account_id=target.account_id if target else None, actor_id=self.actor, actor_kind="admin", action=action, previous_state=previous, new_state=new, reason=reason, details=details or {}, request_id=str(self.request_id)))

    def _post(self, post_id):
        post = self.db.get(SocialPost, post_id)
        if not post:
            raise SocialError("NOT_FOUND", "This social post was not found.", 404)
        return post

    def _revision(self, post):
        revision = self.db.get(SocialPostRevision, post.current_revision_id)
        if not revision or revision.post_id != post.id:
            raise SocialError("SOCIAL_SCHEMA_UNAVAILABLE", "This draft revision is unavailable. Ask an administrator to verify the social schema.", 503)
        return revision

    def _publication(self, post):
        return self.db.scalar(select(SocialPublication).where(SocialPublication.post_id == post.id, SocialPublication.revoked_at.is_(None)))

    def _targets(self, publication):
        return list(self.db.scalars(select(SocialPostTarget).where(SocialPostTarget.publication_id == publication.id).order_by(SocialPostTarget.id))) if publication else []

    def _locked(self, post_id, expected_version):
        require_positive_version(expected_version)
        post = self._post(post_id)
        revision = self._revision(post)
        publication = self._publication(post)
        accounts = {t.account_id for t in PostDocument.model_validate(revision.document).targets}
        if publication:
            accounts.update(t.account_id for t in self._targets(publication))
        # Same order as worker dispatch permits: controls, accounts, publication, targets.
        self.db.scalar(select(SocialControls).where(SocialControls.id == 1).with_for_update().execution_options(populate_existing=True))
        if accounts:
            list(self.db.scalars(select(SocialAccount).where(SocialAccount.id.in_(accounts)).order_by(SocialAccount.id).with_for_update().execution_options(populate_existing=True)))
        if publication:
            publication = self.db.scalar(select(SocialPublication).where(SocialPublication.id == publication.id).with_for_update().execution_options(populate_existing=True))
            list(self.db.scalars(select(SocialPostTarget).where(SocialPostTarget.publication_id == publication.id).order_by(SocialPostTarget.id).with_for_update().execution_options(populate_existing=True)))
        post = self.db.scalar(select(SocialPost).where(SocialPost.id == post_id).with_for_update().execution_options(populate_existing=True))
        if post.row_version != expected_version:
            raise SocialError("VERSION_CONFLICT", "This post changed. Refresh it before continuing.")
        return post, self._revision(post), self._publication(post)

    def _touch(self, post):
        post.row_version += 1
        post.updated_at = self.now()

    def _new_revision(self, post, document, references, revision_no):
        ids = all_asset_ids(document)
        assets = list(self.db.scalars(select(SocialMediaAsset).where(SocialMediaAsset.id.in_(ids))
            .order_by(SocialMediaAsset.id).with_for_update().execution_options(populate_existing=True))) if ids else []
        if ids != {asset.id for asset in assets}:
            raise SocialError("TARGET_VALIDATION_FAILED", "One or more referenced media assets do not exist.", 422)
        if any(asset.state != 'ready' or asset.deleted_at is not None for asset in assets):
            raise SocialError("TARGET_VALIDATION_FAILED", "Referenced media assets must be ready and available.", 422)
        evidence = {"references": [r.model_dump(mode="json") if hasattr(r, "model_dump") else r for r in references]}
        value = document_json(document)
        revision = SocialPostRevision(id=uuid4(), post_id=post.id, revision_no=revision_no, document=value, content_hash=canonical_hash({"document": value, "evidence_snapshot": evidence}), evidence_snapshot=evidence, created_by=self.actor)
        self.db.add(revision)
        self.db.flush()
        for asset_id in sorted(ids):
            self.db.add(SocialRevisionAsset(revision_id=revision.id, asset_id=asset_id))
        post.current_revision_id = revision.id
        return revision

    def create(self, body, *, duplicated_from=None):
        post = SocialPost(id=uuid4(), origin_type="manual", creation_method="duplicate" if duplicated_from else "admin", title=body.title, content_type=body.content_type, editorial_state="draft", duplicated_from_id=duplicated_from, created_by=self.actor)
        self.db.add(post)
        self.db.flush()
        revision = self._new_revision(post, body.document, body.references, 1)
        self.audit("post.duplicated" if duplicated_from else "post.created", post=post, new="draft", details={"revision_id": str(revision.id), "content_hash": revision.content_hash})
        self.db.flush()
        return self.detail(post.id)

    def _dispatched(self, publication):
        if not publication:
            return False
        return bool(self.db.scalar(select(SocialPublishAttempt.id).join(SocialPostTarget, SocialPublishAttempt.target_id == SocialPostTarget.id).where(SocialPostTarget.publication_id == publication.id, SocialPublishAttempt.dispatch_started_at.is_not(None)).limit(1))) or any(t.state in INFLIGHT or t.submit_count > 0 for t in self._targets(publication))

    def patch(self, post_id, body):
        post, old, publication = self._locked(post_id, body.expected_version)
        # Past revisions are checked as well: revocation cannot reopen dispatched content.
        pubs = list(self.db.scalars(select(SocialPublication).where(SocialPublication.post_id == post.id)))
        if any(self._dispatched(p) for p in pubs):
            raise SocialError("CONTENT_LOCKED", "Dispatch has started. Duplicate this post to make a correction.")
        if not body.model_fields_set - {"expected_version"}:
            raise SocialError("INVALID_REQUEST", "Provide at least one editable field.", 422)
        previous = post.editorial_state
        if publication:
            publication.revoked_at = self.now()
            publication.version += 1
            publication.updated_at = self.now()
            for target in self._targets(publication):
                target.state, target.next_action, target.next_action_at = "cancelled", None, None
                target.lease_owner = target.lease_token = target.lease_expires_at = None
                target.updated_at = self.now()
            self.db.flush()  # clear the active-publication unique index before future approvals.
        if body.title is not None:
            post.title = body.title
        if body.content_type is not None:
            post.content_type = body.content_type
        document = body.document if body.document is not None else PostDocument.model_validate(old.document)
        references = body.references if body.references is not None else old.evidence_snapshot["references"]
        new = self._new_revision(post, document, references, old.revision_no + 1)
        post.editorial_state = "draft"
        self._touch(post)
        self.audit("post.revised", post=post, previous=previous, new="draft", details={"revision_id": str(new.id), "previous_revision_id": str(old.id)})
        self.db.flush()
        return self.detail(post.id)

    def validate(self, post_id, body):
        if body.expected_version is not None:
            require_positive_version(body.expected_version)
        post = self._post(post_id)
        if body.expected_version is not None and post.row_version != body.expected_version:
            raise SocialError("VERSION_CONFLICT", "This post changed. Refresh it before validating.")
        revision = self._revision(post)
        return validate_document(self.db, PostDocument.model_validate(revision.document), revision.evidence_snapshot, self.available_adapters).model_dump(mode="json")

    def submit(self, post_id, body):
        post, revision, publication = self._locked(post_id, body.expected_version)
        if post.editorial_state not in {"draft", "rejected"}:
            raise SocialError("INVALID_STATE", "Only a draft or rejected post can be submitted for review.")
        previous = post.editorial_state
        post.editorial_state = "pending_review"
        self._touch(post)
        self.audit("post.submitted", post=post, previous=previous, new=post.editorial_state, details={"revision_id": str(revision.id)})
        self.db.flush()
        return self.detail(post.id)

    def _validate_authorization(self, post, revision, body):
        if revision.id != body.revision_id:
            raise SocialError("VERSION_CONFLICT", "The selected revision changed. Refresh before approval.")
        if post.editorial_state not in {"draft", "pending_review", "approved"}:
            raise SocialError("INVALID_STATE", "Revise this rejected or archived post before authorizing it.")
        if post.origin_type == "generated" or post.content_type in SENSITIVE_CATEGORIES:
            attestation = body.review_attestation
            if not attestation or not attestation.facts_checked or not attestation.sources_checked or not revision.evidence_snapshot.get("references"):
                raise SocialError("REVIEW_ATTESTATION_REQUIRED", "Verify the financial facts and references, then attest to the review.", 422)
        actual_hash = canonical_hash({"document": revision.document, "evidence_snapshot": revision.evidence_snapshot})
        if actual_hash != revision.content_hash:
            raise SocialError("REVISION_INTEGRITY_FAILED", "The immutable revision hash does not match its content.", 503)
        result = validate_document(self.db, PostDocument.model_validate(revision.document), revision.evidence_snapshot, self.available_adapters)
        if not result.valid:
            raise SocialError("TARGET_VALIDATION_FAILED", "Every selected destination must be valid before authorization.", 422, field_errors=[e.model_dump(mode="json") for e in result.errors], target_errors=[{"account_id": str(t.account_id), **e.model_dump(mode="json")} for t in result.targets for e in t.errors])
        return result

    def _authorize(self, post, revision, publication, body, validation):
        if publication:
            if publication.revision_id != revision.id or publication.approved_hash != revision.content_hash:
                raise SocialError("VERSION_CONFLICT", "The active authorization does not match this revision.")
            if publication.cancel_requested_at:
                raise SocialError("INVALID_STATE", "This publication was cancelled. Create a new revision or duplicate it.")
            return publication
        now = self.now()
        publication = SocialPublication(id=uuid4(), post_id=post.id, revision_id=revision.id, authorization_kind="human", approved_by=self.actor, approved_at=now, approved_hash=revision.content_hash)
        self.db.add(publication)
        self.db.flush()
        for result in validation.targets:
            payload = result.resolved_preview
            self.db.add(SocialPostTarget(id=uuid4(), publication_id=publication.id, account_id=result.account_id, resolved_payload=payload.model_dump(mode="json"), payload_hash=payload.content_hash, capability_version=payload.capability_version, state="ready"))
        previous = post.editorial_state
        post.editorial_state = "approved"
        self.audit("post.approved", post=post, previous=previous, new="approved", details={"publication_id": str(publication.id), "revision_id": str(revision.id), "content_hash": revision.content_hash, "attestation": body.review_attestation.model_dump() if body.review_attestation else None})
        self.db.flush()
        return publication

    def approve(self, post_id, body):
        post, revision, publication = self._locked(post_id, body.expected_version)
        result = self._validate_authorization(post, revision, body)
        self._authorize(post, revision, publication, body, result)
        self._touch(post)
        self.db.flush()
        return self.detail(post.id)

    def reject(self, post_id, body):
        post, revision, publication = self._locked(post_id, body.expected_version)
        if post.editorial_state != "pending_review":
            raise SocialError("INVALID_STATE", "Only a post pending review can be rejected.")
        post.editorial_state = "rejected"
        self._touch(post)
        self.audit("post.rejected", post=post, previous="pending_review", new="rejected", reason=body.reason)
        self.db.flush()
        return self.detail(post.id)

    def _publishing_gates(self, post, revision, body):
        """All outbound admin commands use the same current policy gates."""
        controls = self.db.get(SocialControls, 1)
        if not controls or not controls.publishing_enabled:
            raise SocialError("PUBLISHING_PAUSED", "Publishing is paused. Your draft is preserved.")
        result = self._validate_authorization(post, revision, body)
        codes = {w.code for target in result.targets for w in target.warnings} | {w.code for w in result.warnings}
        if not codes.issubset(set(body.acknowledged_warning_codes)):
            raise SocialError("WARNINGS_NOT_ACKNOWLEDGED", "Review and acknowledge every publication warning.", 422)
        if any(controls.platform_controls.get(t.platform, {}).get("publishing_enabled") is False for t in result.targets):
            raise SocialError("PUBLISHING_PAUSED", "One selected platform is paused. All targets remain unqueued.")
        if any(t.platform == "x" for t in result.targets) and controls.budget_controls.get("x_budget_microusd", 0) <= 0:
            raise SocialError("BUDGET_UNAVAILABLE", "X publishing requires an explicitly approved API budget.")
        return result

    def publish(self, post_id, body, *, scheduled=False):
        post, revision, publication = self._locked(post_id, body.expected_version)
        result = self._publishing_gates(post, revision, body)
        now = self.now()
        try:
            due = resolve_schedule(body.schedule, now) if scheduled else now
        except ValueError:
            raise SocialError("INVALID_SCHEDULE_TIME", "Choose a future civil time and matching timezone offset.", 422) from None
        publication = self._authorize(post, revision, publication, body, result)
        if publication.dispatch_requested_at is not None:
            if scheduled and due != utc(publication.scheduled_for):
                raise SocialError("INVALID_STATE", "This revision is already queued with another schedule. Cancel it and revise the draft before scheduling again.")
            return self.accepted(post, publication)
        # Use the frozen approved targets; never silently replace the selected subset.
        frozen = {t.account_id: t for t in self._targets(publication)}
        if set(frozen) != {t.account_id for t in result.targets}:
            raise SocialError("REVISION_INTEGRITY_FAILED", "Approved destinations do not match the selected revision.", 503)
        for validated in result.targets:
            target = frozen[validated.account_id]
            if target.payload_hash != validated.resolved_preview.content_hash:
                raise SocialError("REVISION_INTEGRITY_FAILED", "The account or media changed after approval. Create and approve a new revision.")
        publication.scheduled_for = due
        publication.schedule_timezone = body.schedule.timezone if scheduled else "UTC"
        publication.requested_local_time = body.schedule.local_time if scheduled else due.replace(tzinfo=None).isoformat()
        publication.start_deadline = due + timedelta(hours=1)
        publication.retry_deadline = due + timedelta(hours=24)
        publication.dispatch_requested_at = now
        publication.version += 1
        publication.updated_at = now
        for target in frozen.values():
            target.state, target.next_action, target.next_action_at = "queued", "publish", due
            target.updated_at = now
        self._touch(post)
        self.audit("post.scheduled" if scheduled else "post.publish_requested", post=post, previous="ready", new="queued", details={"publication_id": str(publication.id), "scheduled_for": iso(due), "timezone": publication.schedule_timezone})
        self.db.flush()
        return self.accepted(post, publication)

    def edit_schedule(self, post_id, body, *, scheduled=False):
        """Move only untouched work; the human authorization and payloads stay frozen."""
        require_positive_version(body.expected_publication_version)
        post, revision, publication = self._locked(post_id, body.expected_version)
        if not publication or publication.id != body.publication_id or publication.version != body.expected_publication_version:
            raise SocialError("VERSION_CONFLICT", "The selected authorization changed. Refresh before adjusting its schedule.")
        if publication.cancel_requested_at or publication.revoked_at or post.editorial_state != "approved":
            raise SocialError("INVALID_STATE", "Only an active approved authorization can change its schedule.")
        now = self.now()
        if any(deadline and now >= utc(deadline) for deadline in (publication.start_deadline, publication.retry_deadline, publication.content_valid_until)):
            raise SocialError("AUTHORIZATION_EXPIRED", "This authorization expired. Create and review a new revision.")
        targets = self._targets(publication)
        # A claim alone is already worker-owned. Never clear or move it here.
        if any(t.state == "claimed" or t.lease_token is not None or t.lease_owner is not None or t.lease_expires_at is not None for t in targets):
            raise SocialError("TARGET_BUSY", "A worker currently owns a destination. Refresh its results before adjusting the schedule.")
        attempted = set(self.db.scalars(select(SocialPublishAttempt.target_id).where(SocialPublishAttempt.target_id.in_([t.id for t in targets]))))
        eligible = [t for t in targets if t.state in {"ready", "queued"} and t.submit_count == 0 and t.id not in attempted and t.checkpoint == {} and t.remote_refs == {} and t.primary_remote_id is None and t.remote_url is None and t.published_at is None and t.confirmation_kind is None and t.visibility_state == "unknown"]
        if not eligible:
            raise SocialError("INVALID_STATE", "There are no untouched unsent destinations to adjust.")
        try:
            document = PostDocument.model_validate(revision.document)
            actual_hash = canonical_hash({"document": revision.document, "evidence_snapshot": revision.evidence_snapshot})
            frozen = {t.account_id: t for t in targets}
            if publication.authorization_kind != "human" or not publication.approved_by or not publication.approved_at or publication.revision_id != revision.id or publication.approved_hash != revision.content_hash or actual_hash != revision.content_hash or len(frozen) != len(targets) or set(frozen) != {t.account_id for t in document.targets}:
                raise ValueError("authorization mismatch")
            for target in targets:
                payload = ResolvedPostPayload.model_validate(target.resolved_payload)
                if payload.account_id != target.account_id or payload.content_hash != target.payload_hash or canonical_hash(payload.model_dump(mode="json", exclude={"content_hash"})) != target.payload_hash:
                    raise ValueError("frozen payload mismatch")
        except (ValueError, TypeError):
            raise SocialError("REVISION_INTEGRITY_FAILED", "The frozen authorization or destination payloads need repair. No schedule was changed.", 503) from None
        controls = self.db.get(SocialControls, 1)
        if not controls or not controls.publishing_enabled:
            raise SocialError("PUBLISHING_PAUSED", "Publishing is paused. The existing schedule was preserved.")
        ids = {t.account_id for t in eligible}
        selected = document.model_copy(update={"targets": tuple(t for t in document.targets if t.account_id in ids)})
        result = validate_document(self.db, selected, revision.evidence_snapshot, self.available_adapters)
        if not result.valid:
            raise SocialError("TARGET_VALIDATION_FAILED", "The unsent destinations need revalidation before adjusting their schedule.", 422, field_errors=[e.model_dump(mode="json") for e in result.errors], target_errors=[{"account_id": str(t.account_id), **e.model_dump(mode="json")} for t in result.targets for e in t.errors])
        if {t.account_id for t in result.targets} != ids or any(frozen[t.account_id].payload_hash != t.resolved_preview.content_hash for t in result.targets):
            raise SocialError("REVISION_INTEGRITY_FAILED", "An unsent destination or media changed. Create and approve a new revision.")
        warnings = [*result.warnings, *(w for t in result.targets for w in t.warnings)]
        missing = [w for w in warnings if w.code not in body.acknowledged_warning_codes]
        if missing:
            raise SocialError("WARNINGS_NOT_ACKNOWLEDGED", "Review and acknowledge the unsent destination warnings.", 422, field_errors=[w.model_dump(mode="json") for w in missing])
        if any(controls.platform_controls.get(t.platform, {}).get("publishing_enabled") is False for t in result.targets):
            raise SocialError("PUBLISHING_PAUSED", "An unsent platform is paused. The schedule was preserved.")
        if any(t.platform == "x" for t in result.targets) and controls.budget_controls.get("x_budget_microusd", 0) <= 0:
            raise SocialError("BUDGET_UNAVAILABLE", "X publishing requires an explicitly approved API budget.")
        try:
            due = resolve_schedule(body.schedule, now) if scheduled else now
        except ValueError:
            raise SocialError("INVALID_SCHEDULE_TIME", "Choose a future civil time and matching timezone offset.", 422) from None
        validity = utc(publication.content_valid_until) if publication.content_valid_until else None
        if validity and due >= validity:
            raise SocialError("AUTHORIZATION_EXPIRED", "The requested time is outside the original content validity. Review a new revision.")
        old_due = iso(publication.scheduled_for)
        publication.scheduled_for = due
        publication.schedule_timezone = body.schedule.timezone if scheduled else "UTC"
        publication.requested_local_time = body.schedule.local_time if scheduled else due.replace(tzinfo=None).isoformat()
        publication.start_deadline = min(due + timedelta(hours=1), validity) if validity else due + timedelta(hours=1)
        publication.retry_deadline = min(due + timedelta(hours=24), validity) if validity else due + timedelta(hours=24)
        publication.dispatch_requested_at = publication.dispatch_requested_at or now
        publication.version += 1
        publication.updated_at = now
        for target in eligible:
            target.state, target.next_action, target.next_action_at = "queued", "publish", due
            target.updated_at = now
        self._touch(post)
        self.audit("post.rescheduled" if scheduled else "post.publish_now_requested", post=post, reason=body.reason, details={"publication_id": str(publication.id), "previous_scheduled_for": old_due, "scheduled_for": iso(due), "timezone": publication.schedule_timezone, "target_ids": [str(t.id) for t in eligible]})
        self.db.flush()
        return self.detail(post.id)

    def cancel(self, post_id, body):
        post, revision, publication = self._locked(post_id, body.expected_version)
        inflight = []
        if publication:
            now = self.now()
            publication.cancel_requested_at = now
            publication.version += 1
            publication.updated_at = now
            targets = self._targets(publication)
            attempted = set(self.db.scalars(select(SocialPublishAttempt.target_id).where(SocialPublishAttempt.target_id.in_([t.id for t in targets]))))
            for target in targets:
                if target.state in INFLIGHT or target.state == "claimed" or target.submit_count > 0 or target.id in attempted or target.lease_token is not None or target.lease_owner is not None or target.lease_expires_at is not None or target.checkpoint != {} or target.remote_refs != {} or target.primary_remote_id is not None:
                    inflight.append(str(target.id))
                elif target.state not in {"failed", "cancelled"}:
                    target.state, target.next_action, target.next_action_at = "cancelled", None, None
                    target.lease_owner = target.lease_token = target.lease_expires_at = None
                    target.updated_at = now
        self._touch(post)
        self.audit("post.cancel_requested", post=post, details={"publication_id": str(publication.id) if publication else None, "in_flight_target_ids": inflight})
        self.db.flush()
        detail = self.detail(post.id)
        detail["cancellation"] = {"in_flight_target_ids": inflight, "message": "Worker-owned or attempted requests are retained until cancellation is acknowledged; remote requests may still complete." if inflight else "Unsent targets are cancelled."}
        return detail

    def resume(self, post_id, body):
        """Resume only unchanged, cancelled work with no external operations."""
        post, revision, publication = self._locked(post_id, body.expected_version)
        if not publication or not publication.cancel_requested_at or publication.revoked_at:
            raise SocialError("INVALID_STATE", "Only a cancelled, active authorization can resume.")
        targets = self._targets(publication)
        attempted = self.db.scalar(select(SocialPublishAttempt.id).join(SocialPostTarget, SocialPublishAttempt.target_id == SocialPostTarget.id).where(SocialPostTarget.publication_id == publication.id).limit(1))
        if attempted or self._dispatched(publication):
            raise SocialError("CONTENT_LOCKED", "An external operation started. Duplicate and review a new post instead.")
        if not targets or any(t.state != "cancelled" for t in targets):
            raise SocialError("INVALID_STATE", "Every destination must be cancelled and unsent before resume.")
        now = self.now()
        if any(deadline and now >= utc(deadline) for deadline in (publication.start_deadline, publication.retry_deadline, publication.content_valid_until)):
            raise SocialError("AUTHORIZATION_EXPIRED", "This authorization expired. Create and review a new revision.")
        result = self._publishing_gates(post, revision, body)
        if publication.revision_id != revision.id or publication.approved_hash != revision.content_hash:
            raise SocialError("REVISION_INTEGRITY_FAILED", "The original authorization does not match this revision.", 503)
        frozen = {t.account_id: t for t in targets}
        if set(frozen) != {t.account_id for t in result.targets} or any(frozen[v.account_id].payload_hash != v.resolved_preview.content_hash for v in result.targets):
            raise SocialError("REVISION_INTEGRITY_FAILED", "Destinations or media changed. Create and review a new revision.")
        due = max(now, utc(publication.scheduled_for)) if publication.scheduled_for else now
        publication.cancel_requested_at = None
        if publication.dispatch_requested_at is None:
            publication.dispatch_requested_at = now
            publication.scheduled_for = due
            publication.schedule_timezone = "UTC"
            publication.requested_local_time = due.replace(tzinfo=None).isoformat()
            publication.start_deadline = due + timedelta(hours=1)
            publication.retry_deadline = due + timedelta(hours=24)
        publication.version += 1
        publication.updated_at = now
        for target in targets:
            target.state, target.next_action, target.next_action_at = "queued", "publish", due
            target.updated_at = now
        self._touch(post)
        self.audit("post.resumed", post=post, previous="cancelled", new="queued", reason=body.reason, details={"publication_id": str(publication.id), "scheduled_for": iso(due), "revision_id": str(revision.id)})
        self.db.flush()
        return self.accepted(post, publication)

    def duplicate(self, post_id, body):
        from .contracts import CreatePost
        post, revision, publication = self._locked(post_id, body.expected_version)
        return self.create(CreatePost(title=post.title, content_type=post.content_type, document=PostDocument.model_validate(revision.document), references=revision.evidence_snapshot.get("references", [])), duplicated_from=post.id)

    def retry(self, target_id, body):
        initial = self.db.get(SocialPostTarget, target_id)
        if not initial:
            raise SocialError("NOT_FOUND", "This destination was not found.", 404)
        controls = self.db.scalar(select(SocialControls).where(SocialControls.id == 1).with_for_update())
        account = self.db.scalar(select(SocialAccount).where(SocialAccount.id == initial.account_id).with_for_update())
        publication = self.db.scalar(select(SocialPublication).where(SocialPublication.id == initial.publication_id).with_for_update())
        target = self.db.scalar(select(SocialPostTarget).where(SocialPostTarget.id == target_id).with_for_update().execution_options(populate_existing=True))
        if target.state in {"outcome_unknown", "reconciling", "dispatching", "processing"}:
            raise SocialError("RECONCILIATION_REQUIRED", "The prior send may have been accepted. Reconcile it before any retry.")
        if target.state != "failed" or target.primary_remote_id or target.published_at:
            raise SocialError("RETRY_NOT_SAFE", "Only an eligible failed destination can be retried.")
        latest = self.db.scalar(select(SocialPublishAttempt).where(SocialPublishAttempt.target_id == target.id).order_by(SocialPublishAttempt.sequence.desc()).limit(1))
        receipt = latest.receipt if latest and isinstance(latest.receipt, dict) else {}
        if not latest or latest.outcome != "definite_failure" or receipt.get("retry_safe") is not True:
            raise SocialError("RETRY_NOT_SAFE", "The recorded operation does not establish a safe retry.")
        now = self.now()
        if publication.revoked_at or publication.cancel_requested_at or target.submit_count >= 5 or (publication.retry_deadline and now >= utc(publication.retry_deadline)) or (publication.content_valid_until and now >= utc(publication.content_valid_until)):
            raise SocialError("RETRY_NOT_SAFE", "This authorization is cancelled, expired or exhausted. Review a new draft.")
        if not controls or not controls.publishing_enabled:
            raise SocialError("PUBLISHING_PAUSED", "Publishing is paused; retry remains unqueued.")
        caps = capability_for(account, self.available_adapters)
        if account.connection_state != "connected" or not account.publishing_enabled or account.hold_reason or not caps.eligible:
            raise SocialError("ACCOUNT_UNAVAILABLE", "Reconnect and validate the failed account before retry.")
        if not caps.adapter_available:
            raise SocialError("ADAPTER_NOT_AVAILABLE", "The platform adapter is unavailable in this batch.")
        if controls.platform_controls.get(account.platform, {}).get("publishing_enabled") is False:
            raise SocialError("PUBLISHING_PAUSED", "This platform is paused; retry remains unqueued.")
        if account.platform == "x" and controls.budget_controls.get("x_budget_microusd", 0) <= 0:
            raise SocialError("BUDGET_UNAVAILABLE", "X retry requires an explicitly approved API budget.")
        revision = self.db.get(SocialPostRevision, publication.revision_id)
        document = PostDocument.model_validate(revision.document)
        selected = tuple(t for t in document.targets if t.account_id == target.account_id)
        if len(selected) != 1:
            raise SocialError("REVISION_INTEGRITY_FAILED", "The failed destination is absent from its authorized revision.", 503)
        validation = validate_document(self.db, document.model_copy(update={"targets": selected}), revision.evidence_snapshot, self.available_adapters)
        if not validation.valid:
            raise SocialError("TARGET_VALIDATION_FAILED", "The failed destination needs revalidation before retry.", 422, target_errors=[{"account_id": str(t.account_id), **e.model_dump(mode="json")} for t in validation.targets for e in t.errors])
        if validation.targets[0].resolved_preview.content_hash != target.payload_hash:
            raise SocialError("REVISION_INTEGRITY_FAILED", "The failed destination's account or media changed. Create and approve a new revision.")
        post = self._post(publication.post_id)
        target.state, target.next_action, target.next_action_at = "retry_wait", "publish", now
        target.error_code = target.safe_error_message = None
        target.updated_at = now
        self._touch(post)
        self.audit("target.retry_requested", post=post, target=target, previous="failed", new="retry_wait", reason=body.reason)
        self.db.flush()
        return self.detail(post.id)

    def controls(self, body):
        require_positive_version(body.expected_version)
        controls = self.db.scalar(select(SocialControls).where(SocialControls.id == 1).with_for_update())
        if not controls:
            if self.db.bind.dialect.name == "postgresql":
                self.db.execute(text("SELECT pg_advisory_xact_lock(6384952001)"))
                controls = self.db.scalar(select(SocialControls).where(SocialControls.id == 1).with_for_update())
            if not controls:
                controls = SocialControls(id=1, version=1)
                self.db.add(controls)
                self.db.flush()
        if controls.version != body.expected_version:
            raise SocialError("VERSION_CONFLICT", "Publishing controls changed. Refresh before updating.")
        controls.publishing_enabled = body.publishing_enabled
        controls.version += 1
        controls.updated_by, controls.updated_at = self.actor, self.now()
        self.audit("controls.updated", reason=body.reason, details={"publishing_enabled": controls.publishing_enabled, "version": controls.version})
        self.db.flush()
        return {"version": controls.version, "publishing_enabled": controls.publishing_enabled, "generation_enabled": False, "auto_approve_enabled": False, "auto_schedule_enabled": False, "auto_publish_enabled": False}

    def _target_dto(self, target):
        return {"id": str(target.id), "account_id": str(target.account_id), "platform": target.resolved_payload["platform"], "state": target.state, "remote_url": target.remote_url, "safe_error_message": target.safe_error_message, "next_action_at": iso(target.next_action_at), "published_at": iso(target.published_at)}

    def _delivery(self, targets, publication, now=None):
        states = {t.state for t in targets}
        if not states or states == {"ready"}:
            return "not_requested"
        if states & {"outcome_unknown", "reconciling"}:
            return "needs_attention"
        if states == {"published"}:
            return "published"
        if "published" in states:
            return "partially_published"
        if states == {"cancelled"}:
            return "cancelled"
        if states <= {"failed", "cancelled"}:
            return "failed"
        if "blocked" in states:
            return "needs_attention"
        if states & {"claimed", "dispatching", "processing", "retry_wait"}:
            return "publishing"
        if publication and publication.scheduled_for and utc(publication.scheduled_for) > (now or self.now()):
            return "scheduled"
        return "queued"

    def _publication_dto(self, publication):
        return {"id": str(publication.id), "revision_id": str(publication.revision_id), "version": publication.version, "approved_at": iso(publication.approved_at), "approved_by": str(publication.approved_by), "scheduled_for": iso(publication.scheduled_for), "schedule_timezone": publication.schedule_timezone, "requested_local_time": publication.requested_local_time, "cancel_requested_at": iso(publication.cancel_requested_at)} if publication else None

    def _compact_publications(self, post_ids):
        from types import SimpleNamespace
        fields = (SocialPublication.id, SocialPublication.post_id, SocialPublication.revision_id, SocialPublication.version, SocialPublication.approved_at, SocialPublication.approved_by, SocialPublication.scheduled_for, SocialPublication.schedule_timezone, SocialPublication.requested_local_time, SocialPublication.cancel_requested_at)
        return {row.post_id: SimpleNamespace(**row._mapping) for row in self.db.execute(select(*fields).where(SocialPublication.post_id.in_(post_ids), SocialPublication.revoked_at.is_(None)))} if post_ids else {}

    def _summary(self, post, publication, targets, now=None, history=None):
        historical = history or {"targets": [], "total": 0}
        return {"id": str(post.id), "title": post.title, "content_type": post.content_type, "origin_type": post.origin_type, "editorial_state": post.editorial_state, "delivery_status": self._delivery(targets, publication, now), "version": post.row_version, "revision_id": str(post.current_revision_id), "created_at": iso(post.created_at), "created_by": str(post.created_by) if post.created_by else None, "updated_at": iso(post.updated_at), "targets": [self._target_dto(t) for t in targets], "publication": self._publication_dto(publication), "historical_targets": historical["targets"], "historical_target_count": historical["total"]}

    def detail(self, post_id):
        post = self._post(post_id)
        revision = self._revision(post)
        publication = self._publication(post)
        result = self._summary(post, publication, self._targets(publication), history=self._compact_history([post.id]).get(post.id))
        result.update(document=revision.document, references=revision.evidence_snapshot.get("references", []))
        return result

    def posts(self, page=1, page_size=20, editorial_state=None, delivery_filter="all"):
        if type(page) is not int or not 1 <= page <= 2_147_483_647 or type(page_size) is not int or not 1 <= page_size <= 100:
            raise SocialError("INVALID_REQUEST", "Choose a valid post page and page size.", 422)
        if delivery_filter not in {"all", "scheduled", "history", "needs_attention"}:
            raise SocialError("INVALID_REQUEST", "Choose a supported delivery filter.", 422)
        now = self.now()
        condition = [SocialPost.editorial_state == editorial_state] if editorial_state else []
        if delivery_filter != "all":
            membership = [SocialPublication.post_id == SocialPost.id]
            if delivery_filter == "scheduled":
                membership += [SocialPublication.revoked_at.is_(None), SocialPublication.cancel_requested_at.is_(None), SocialPostTarget.state.in_(("ready", "queued")), SocialPostTarget.submit_count == 0, func.coalesce(SocialPostTarget.next_action_at, SocialPublication.scheduled_for) > now]
            else:
                states = ("published", "failed", "cancelled", "outcome_unknown") if delivery_filter == "history" else ("failed", "blocked", "reconciling", "outcome_unknown")
                membership.append(SocialPostTarget.state.in_(states))
            condition.append(select(SocialPostTarget.id).join(SocialPublication, SocialPostTarget.publication_id == SocialPublication.id).where(*membership).exists())
        # Count and page use one statement/snapshot, including an empty late page.
        filtered = select(SocialPost.id).where(*condition).cte("filtered_posts")
        count = select(func.count().label("total")).select_from(filtered).cte("matching_count")
        page_rows = select(SocialPost).join(filtered, SocialPost.id == filtered.c.id).order_by(SocialPost.updated_at.desc(), SocialPost.id).offset((page - 1) * page_size).limit(page_size).cte("post_page")
        rows = self.db.execute(select(page_rows, count.c.total).select_from(count.outerjoin(page_rows, true())).order_by(page_rows.c.updated_at.desc(), page_rows.c.id)).all()
        from types import SimpleNamespace
        posts = [SimpleNamespace(**{k: v for k, v in row._mapping.items() if k != "total"}) for row in rows if row.id is not None]
        total = rows[0].total
        pubs = self._compact_publications([p.id for p in posts])
        grouped = self._compact_targets([p.id for p in pubs.values()])
        history = self._compact_history([p.id for p in posts])
        return {"posts": [self._summary(p, pubs.get(p.id), grouped.get(pubs[p.id].id, []) if p.id in pubs else [], now, history.get(p.id)) for p in posts], "total": total, "page": page, "page_size": page_size, "has_more": page * page_size < total}

    def _history_projection(self):
        # Historical delivery receipts never load payloads, revisions or grants.
        target, publication = SocialPostTarget, SocialPublication
        return select(target.id, target.publication_id, publication.post_id, publication.revision_id,
            target.account_id, SocialAccount.platform, target.state, target.remote_url, target.safe_error_message,
            target.next_action_at, target.published_at, target.updated_at, publication.approved_at,
            publication.approved_by, publication.scheduled_for, publication.cancel_requested_at, publication.revoked_at
        ).join(publication, target.publication_id == publication.id).join(SocialAccount, target.account_id == SocialAccount.id
        ).where(target.state.in_(("published", "failed", "cancelled", "outcome_unknown", "blocked", "reconciling")))

    def _historical_target_dto(self, row):
        return {key: str(row[key]) if key in {"id", "publication_id", "revision_id", "account_id", "approved_by"}
            else iso(row[key]) if key in {"next_action_at", "published_at", "updated_at", "approved_at", "scheduled_for", "cancel_requested_at", "revoked_at"}
            else row[key] for key in row if key not in {"post_id", "history_rank", "history_count", "total"}}

    def _compact_history(self, post_ids):
        if not post_ids:
            return {}
        target, publication = SocialPostTarget, SocialPublication
        ranked = self._history_projection().add_columns(
            func.row_number().over(partition_by=publication.post_id, order_by=(target.updated_at.desc(), target.id)).label("history_rank"),
            func.count().over(partition_by=publication.post_id).label("history_count")
        ).where(publication.post_id.in_(post_ids)).cte("ranked_delivery_history")
        rows = self.db.execute(select(ranked).where(ranked.c.history_rank <= 20).order_by(ranked.c.post_id, ranked.c.history_rank)).mappings()
        grouped = {}
        for row in rows:
            history = grouped.setdefault(row["post_id"], {"targets": [], "total": row["history_count"]})
            history["targets"].append(self._historical_target_dto(row))
        return grouped

    def history(self, post_id, page=1, page_size=20):
        self._post(post_id)
        if type(page) is not int or not 1 <= page <= 2_147_483_647 or type(page_size) is not int or not 1 <= page_size <= 20:
            raise SocialError("INVALID_REQUEST", "Choose a valid delivery history page.", 422)
        receipts = self._history_projection().where(SocialPublication.post_id == post_id).cte("delivery_history")
        count = select(func.count().label("total")).select_from(receipts).cte("history_count")
        page_rows = select(receipts).order_by(receipts.c.updated_at.desc(), receipts.c.id).offset((page - 1) * page_size).limit(page_size).cte("history_page")
        rows = self.db.execute(select(page_rows, count.c.total).select_from(count.outerjoin(page_rows, true())).order_by(page_rows.c.updated_at.desc(), page_rows.c.id)).mappings().all()
        total = rows[0]["total"]
        return {"post_id": str(post_id), "targets": [self._historical_target_dto(row) for row in rows if row["id"] is not None],
            "total": total, "page": page, "page_size": page_size, "has_more": page * page_size < total}

    def _compact_targets(self, publication_ids):
        # Explicit projection excludes resolved payloads, receipts and checkpoints.
        rows = self.db.execute(select(SocialPostTarget.id, SocialPostTarget.publication_id, SocialPostTarget.account_id, SocialAccount.platform, SocialPostTarget.state, SocialPostTarget.remote_url, SocialPostTarget.safe_error_message, SocialPostTarget.next_action_at, SocialPostTarget.published_at).join(SocialAccount, SocialPostTarget.account_id == SocialAccount.id).where(SocialPostTarget.publication_id.in_(publication_ids)).order_by(SocialPostTarget.publication_id, SocialPostTarget.id)).all() if publication_ids else []
        from types import SimpleNamespace
        grouped = {}
        for row in rows:
            item = SimpleNamespace(**row._mapping, resolved_payload={"platform": row.platform})
            grouped.setdefault(row.publication_id, []).append(item)
        return grouped

    def summary(self, post_id):
        post = self._post(post_id)
        publication = self._compact_publications([post.id]).get(post.id)
        targets = self._compact_targets([publication.id]).get(publication.id, []) if publication else []
        return self._summary(post, publication, targets, self.now(), self._compact_history([post.id]).get(post.id))

    def accounts(self):
        from types import SimpleNamespace
        fields = (SocialAccount.id, SocialAccount.platform, SocialAccount.display_name,
                  SocialAccount.handle, SocialAccount.profile_url, SocialAccount.connection_state,
                  SocialAccount.publishing_enabled, SocialAccount.capability_snapshot,
                  SocialAccount.api_product, SocialAccount.external_account_id, SocialAccount.granted_scopes)
        accounts = (SimpleNamespace(**row._mapping) for row in self.db.execute(
            select(*fields).order_by(SocialAccount.display_name, SocialAccount.id).limit(100)))
        return {"accounts": [{"id": str(a.id), "platform": a.platform, "display_name": a.display_name, "handle": a.handle, "profile_url": a.profile_url, "connection_state": a.connection_state, "publishing_enabled": a.publishing_enabled, "capabilities": capability_for(a, self.available_adapters).model_dump(mode="json")} for a in accounts]}

    def platforms(self):
        from .contracts import CapabilitySet
        return {"platforms": [{"platform": platform, "capabilities": CapabilitySet().model_dump(mode="json")} for platform in ("facebook", "instagram", "threads", "x", "tiktok")]}

    def status(self):
        from .media.runtime import media_runtime
        controls = self.db.get(SocialControls, 1)
        heart = self.db.scalar(select(SocialWorkerHeartbeat).order_by(SocialWorkerHeartbeat.heartbeat_at.desc()).limit(1))
        now = self.now()
        worker_state = "unavailable"
        if heart and heart.state in {"active", "idle", "stopped"}:
            age = (now - utc(heart.heartbeat_at)).total_seconds()
            scan_age = (now - utc(heart.last_scan_at)).total_seconds() if heart.last_scan_at else None
            fresh_limit = 45 if heart.state == "active" else 150
            if age < -5 or (scan_age is not None and scan_age < -5):
                worker_state = "unavailable"
            elif age > fresh_limit or (scan_age is not None and scan_age > fresh_limit):
                worker_state = "stale"
            elif heart.state in {"active", "idle"} and scan_age is None:
                worker_state = "unavailable"
            else:
                worker_state = heart.state
        counts = dict(self.db.execute(select(SocialPostTarget.state, func.count()).group_by(SocialPostTarget.state)).all())
        available = sorted({key[0] if isinstance(key, tuple) else key for key in self.available_adapters})
        return {"publishing_enabled": bool(controls and controls.publishing_enabled), "controls_version": controls.version if controls else 1, "worker": {"state": worker_state, "heartbeat_at": iso(heart.heartbeat_at) if heart else None, "last_scan_at": iso(heart.last_scan_at) if heart else None}, "queue_counts": counts, "adapters_available": available, "media_upload_available": bool(media_runtime().available_mimes()), "generation_enabled": False, "auto_approve_enabled": False, "auto_schedule_enabled": False, "auto_publish_enabled": False}

    def accepted(self, post, publication):
        targets = self._targets(publication)
        return {"post_id": str(post.id), "publication_id": str(publication.id), "status": "queued", "scheduled_for": iso(publication.scheduled_for), "targets": [{"id": str(t.id), "account_id": str(t.account_id), "platform": t.resolved_payload["platform"], "status": t.state} for t in targets], "status_url": f"/api/v1/admin/social/posts/{post.id}/status"}
