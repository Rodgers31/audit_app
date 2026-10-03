from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from social.contracts import (MasterContent, OperationResult, PostDocument, ScheduleTime, SparseOverrides, VersionCommand, canonical_hash)
from social.validation import resolve_fields, resolve_schedule, validate_document
from test_domain_support import account, db, draft_body


def test_sparse_inheritance_and_intentional_empty_are_distinct():
    target = {"account_id": str(uuid4()), "format": "text", "overrides": {"text": {"mode": "replace", "value": ""}, "link": {"mode": "replace", "value": None}, "hashtags": {"mode": "replace", "value": []}, "media": {"mode": "replace", "value": []}}}
    doc = PostDocument.model_validate({"master": {"text": "master", "link": "https://example.org", "hashtags": ["Audit"], "media": []}, "targets": [target]})
    resolved = resolve_fields(doc, doc.targets[0])
    assert resolved == {"text": "", "link": None, "hashtags": [], "media": []}
    reset = PostDocument.model_validate({"master": doc.master.model_dump(mode="json"), "targets": [{**target, "overrides": {}}]})
    assert resolve_fields(reset, reset.targets[0])["text"] == "master"
    assert canonical_hash(resolved) != canonical_hash(resolve_fields(reset, reset.targets[0]))


@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, "1", float("nan"), float("inf")])
def test_version_rejects_nonpositive_and_coercions(value):
    with pytest.raises(ValidationError):
        VersionCommand(expected_version=value)


def test_documents_reject_unknown_fields_duplicate_accounts_null_and_nan():
    account_id = str(uuid4())
    for overrides in ({"text": None}, {"media": {"mode": "replace", "value": None}}, {"text": {"mode": "replace", "value": float("nan")}}, {"secret_url": "https://secret.example"}):
        with pytest.raises(ValidationError):
            SparseOverrides.model_validate(overrides)
    with pytest.raises(ValidationError):
        PostDocument.model_validate({"schema_version": True, "master": {}})
    with pytest.raises(ValidationError):
        PostDocument.model_validate({"master": {}, "targets": [{"account_id": account_id, "format": "text"}] * 2})
    with pytest.raises(ValueError):
        canonical_hash({"value": float("nan")})
    with pytest.raises(ValidationError):
        OperationResult(outcome="ambiguous", next_action_at=datetime(2026, 10, 1))
    with pytest.raises(ValidationError):
        OperationResult(outcome="ambiguous", checkpoint={"nan": float("nan")})


@pytest.mark.parametrize("url", ["http://example.com", "/relative", "https://user:secret@example.com", "https://", "https://example.com/ white"])
def test_links_require_absolute_https_without_secrets(url):
    with pytest.raises(ValidationError):
        MasterContent(link=url)


def test_no_selected_account_invalid_for_publication(db):
    result = validate_document(db, draft_body().document, {})
    assert not result.valid
    assert result.errors[0].code == "NO_TARGETS"


def test_invalid_selected_account_is_not_silently_removed(db):
    good = account(db)
    doc = draft_body((good,)).document.model_dump(mode="json")
    doc["targets"].append({"account_id": str(uuid4()), "format": "text", "overrides": {}})
    result = validate_document(db, PostDocument.model_validate(doc), {}, {"facebook"})
    assert not result.valid
    assert len(result.targets) == 2
    assert result.targets[0].valid
    assert result.targets[1].errors[0].code == "ACCOUNT_UNAVAILABLE"
    frozen = result.targets[0].resolved_preview
    assert canonical_hash(frozen.model_dump(mode="json", exclude={"content_hash"})) == frozen.content_hash


def test_runtime_adapters_default_unavailable_even_with_capability_flag(db):
    row = account(db)
    result = validate_document(db, draft_body((row,)).document, {})
    assert "ADAPTER_NOT_AVAILABLE" in {e.code for e in result.targets[0].errors}


def test_dst_gap_and_offset_selection():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        resolve_schedule(ScheduleTime(local_time="2026-03-08T02:30:00", timezone="America/Chicago", utc_offset="-06:00"), now)
    first = resolve_schedule(ScheduleTime(local_time="2026-11-01T01:30:00", timezone="America/Chicago", utc_offset="-05:00"), now)
    second = resolve_schedule(ScheduleTime(local_time="2026-11-01T01:30:00", timezone="America/Chicago", utc_offset="-06:00"), now)
    assert (second - first).total_seconds() == 3600
    for civil, zone, offset in [("2026-11-01T01:30:00", "America/Chicago", "-04:00"), ("2026-10-01T10:00:00Z", "UTC", "+00:00"), ("2026-10-01T10:00:00", "Invalid/Zone", "+00:00")]:
        with pytest.raises(ValueError):
            resolve_schedule(ScheduleTime(local_time=civil, timezone=zone, utc_offset=offset), now)


def test_media_order_accessibility_account_and_overrides_change_hash(db):
    from social.models import SocialMediaAsset
    from social.service import document_json
    from test_domain_support import ACTOR
    rows = (account(db), account(db))
    assets = []
    for index in (1, 2):
        asset = SocialMediaAsset(id=uuid4(), storage_provider="fixture", bucket="fixture", storage_key=str(index), original_filename="chart.png", mime_type="image/png", byte_size=100, sha256=str(index) * 64, width=640, height=640, state="ready", created_by=ACTOR)
        db.add(asset)
        assets.append(asset)
    db.commit()
    media = [{"asset_id": str(a.id), "alt_text": "Accessible description"} for a in assets]
    def payload_hash(media_values, identity, overrides):
        doc = PostDocument.model_validate({"master": {"text": "Master", "media": media_values}, "targets": [{"account_id": str(identity.id), "format": "carousel", "overrides": overrides}]})
        result = validate_document(db, doc, {}, {"facebook"})
        assert result.valid
        return result.targets[0].resolved_preview.content_hash
    original = payload_hash(media, rows[0], {})
    assert payload_hash(list(reversed(media)), rows[0], {}) != original
    assert payload_hash(media, rows[1], {}) != original
    assert payload_hash(media, rows[0], {"text": {"mode": "replace", "value": ""}}) != original
    changed_alt = [{**m, "alt_text": "Changed description"} for m in media]
    assert payload_hash(changed_alt, rows[0], {}) != original


@pytest.mark.parametrize("snapshot", [{}, {"eligible": True, "supported_formats": ["text"], "limits": {"max_text_length": True}}, {"eligible": True, "supported_formats": ["text"], "limits": {"max_text_length": float("nan")}}, {"eligible": True, "unknown": "ignored?"}])
def test_malformed_capabilities_fail_closed(db, snapshot):
    row = account(db)
    row.capability_snapshot = snapshot
    db.commit()
    result = validate_document(db, draft_body((row,)).document, {}, {"facebook"})
    assert not result.valid
    assert any(e.code == "ACCOUNT_UNAVAILABLE" for e in result.targets[0].errors)


def test_public_proof_rejects_whitespace_and_unsafe_provider_url():
    for fields in [{"primary_remote_id": " "}, {"confirmation_kind": "\t "}, {"remote_url": "javascript:alert(1)"}, {"remote_url": "https://user:token@example.org/post"}]:
        with pytest.raises(ValidationError):
            OperationResult(outcome="confirmed_success", visibility_state="public", **fields)
    with pytest.raises(ValidationError):
        OperationResult(outcome="ambiguous", checkpoint={"bytes": b"private"})
    value = OperationResult(outcome="confirmed_success", primary_remote_id="opaque/id-9223372036854775808", confirmation_kind="provider_receipt", remote_url="https://example.org/post")
    assert value.primary_remote_id == "opaque/id-9223372036854775808"


@pytest.mark.parametrize("field, value", [("verified", False), ("coverage_complete", False), ("verified", 1), ("coverage_complete", 1), ("verified", "true"), ("coverage_complete", None)])
def test_absence_proof_requires_strict_positive_and_complete_evidence(field, value):
    from social.contracts import DefinitiveAbsenceProof
    data = {"kind": "provider_definitive_status", "verified": True, "coverage_complete": True, "account_id": str(uuid4()), "operation_id": str(uuid4())}
    data[field] = value
    with pytest.raises(ValidationError):
        DefinitiveAbsenceProof.model_validate(data)


def test_reconciliation_generic_evidence_never_becomes_an_absence_proof():
    from social.contracts import DefinitiveAbsenceProof, ReconciliationResult
    data = {"kind": "confirmed_not_sent", "verified": True, "coverage_complete": True, "account_id": str(uuid4()), "operation_id": str(uuid4())}
    proof = DefinitiveAbsenceProof.model_validate(data)
    assert proof.account_id == UUID(data["account_id"])
    result = ReconciliationResult(outcome="definitively_unpublished", evidence={"lookup_succeeded": False, "matches": []})
    assert result.absence_proof is None
    valid = ReconciliationResult(outcome="definitively_unpublished", absence_proof=proof)
    assert valid.absence_proof == proof
    for malformed in ({}, {**data, "kind": "incomplete_lookup"}, {**data, "account_id": "bad"}, {**data, "operation_id": True}, {**data, "unknown": "field"}):
        with pytest.raises(ValidationError):
            ReconciliationResult(outcome="definitively_unpublished", absence_proof=malformed)
