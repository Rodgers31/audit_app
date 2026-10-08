"""Bounded offline review of declarations, never storage or receipt authority.

No environment, clock, files, database, subprocess or network is consulted.
Caller-supplied scope and as-of time are required independently of the packet.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from ipaddress import IPv4Address
import hashlib
import json
import re
from typing import Annotated, Literal, Union
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, StringConstraints, field_validator

MAX_JSON_BYTES = 128 * 1024
MAX_STRING = 2048
MAX_MEDIA_BYTES = 50 * 1024 * 1024
MAX_EVIDENCE_AGE = timedelta(hours=24)
GATES = ("privacy", "least_privilege", "signed_put", "browser_cors", "host_inspection", "storage_accounting", "hosting_profile")
Digest = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]
Commit = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{40}$")]
Label = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")]
Bucket = Annotated[str, StringConstraints(strict=True, min_length=3, max_length=63, pattern=r"^[a-z0-9][a-z0-9.-]*[a-z0-9]$")]
Header = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9-]*$")]
Mime = Literal["image/jpeg", "image/png", "video/mp4"]
Run = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")]
Count = Annotated[int, Field(strict=True, ge=0, le=10**12)]
HTTPStatus = Annotated[int, Field(strict=True, ge=100, le=599)]


class PacketError(ValueError):
    """A fixed local code; no input or nested validation message is exposed."""

    def __init__(self):
        super().__init__("MEDIA_ACCEPTANCE_INVALID_JSON")


def _bounded(value, depth=0, count=None):
    count = [0] if count is None else count
    count[0] += 1
    if depth > 12 or count[0] > 4096:
        raise PacketError()
    if type(value) is dict:
        if len(value) > 64 or any(type(k) is not str or len(k) > 64 for k in value):
            raise PacketError()
        for item in value.values():
            _bounded(item, depth + 1, count)
    elif type(value) is list:
        if len(value) > 32:
            raise PacketError()
        for item in value:
            _bounded(item, depth + 1, count)
    elif type(value) is str:
        if len(value) > MAX_STRING or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise PacketError()
    elif type(value) is int:
        if abs(value) > 10**12:
            raise PacketError()
    elif type(value) not in (bool, type(None)):
        raise PacketError()


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def _check(value):
    _bounded(value)
    if len(_canonical(value)) > MAX_JSON_BYTES:
        raise PacketError()


def parse_json(raw):
    """Decode one bounded UTF-8 object; reject duplicate keys at every depth."""
    try:
        if type(raw) not in (str, bytes) or len(raw) > MAX_JSON_BYTES:
            raise PacketError()
        raw = raw.decode("utf-8") if type(raw) is bytes else raw
        if len(raw.encode("utf-8")) > MAX_JSON_BYTES:
            raise PacketError()
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise PacketError()
                result[key] = value
            return result
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(PacketError()))
        if type(value) is not dict:
            raise PacketError()
        _check(value)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        pass
    # Suppressing display with ``from None`` still retains raw decoder input in
    # __context__. Raise after leaving the handler, with no decoder exception.
    raise PacketError()


def _time(value):
    if type(value) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-](?:0[0-9]|1[0-4]):[0-5][0-9])", value):
        raise ValueError("Invalid explicit timestamp")
    if value[-6:-3] in ("+14", "-14") and value[-2:] != "00":
        raise ValueError("Invalid explicit timestamp")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _origin(value, *, wildcard=False):
    if wildcard and value == "*":
        return value
    if (type(value) is not str or not value.startswith("https://") or "?" in value or "#" in value or len(value) > 253
            or not value.isascii() or any(c.isspace() for c in value)):
        raise ValueError("Invalid browser origin")
    parts = urlsplit(value)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or parts.path or parts.query or parts.fragment or parts.netloc != parts.netloc.lower()
            or not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*(?::[1-9][0-9]{0,4})?", parts.netloc)
            or (parts.port is not None and (parts.port == 443 or not 1 <= parts.port <= 65535))):
        raise ValueError("Invalid browser origin")
    # WHATWG treats a final numeric/hex label as an IPv4 address, including
    # abbreviated, integer and octal forms. Accept only its canonical spelling.
    last_label = parts.hostname.rsplit(".", 1)[-1]
    if re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]*)", last_label):
        if str(IPv4Address(parts.hostname)) != parts.hostname:
            raise ValueError("Invalid browser origin")
    return value


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False, hide_input_in_errors=True)

    def __repr__(self):
        return type(self).__name__ + "()"

    def __str__(self):
        return repr(self)

    @field_validator("*", mode="after")
    @classmethod
    def unique_list_entries(cls, value):
        if isinstance(value, list):
            entries = [_canonical(item.model_dump() if isinstance(item, BaseModel) else item) for item in value]
            if len(set(entries)) != len(entries):
                raise ValueError("Duplicate declaration entries")
        return value


class _Scope(_Model):
    purpose: Literal["social_media_490"]
    storage_endpoint: StrictStr
    bucket: Bucket
    browser_origin: StrictStr
    host_id: Label
    build_commit: Commit
    config_sha256: Digest
    required_mime_types: Annotated[list[Mime], Field(min_length=2, max_length=3)]

    @field_validator("storage_endpoint")
    @classmethod
    def endpoint(cls, value):
        if not re.fullmatch(r"https://[a-f0-9]{32}\.r2\.cloudflarestorage\.com", value):
            raise ValueError("Invalid canonical private endpoint")
        return value

    @field_validator("browser_origin")
    @classmethod
    def origin(cls, value):
        return _origin(value)

    @field_validator("required_mime_types")
    @classmethod
    def formats(cls, value):
        if len(set(value)) != len(value) or not {"image/jpeg", "image/png"} <= set(value):
            raise ValueError("Invalid inspected format slice")
        return value


class _Evidence(_Model):
    scope: _Scope
    run_id: Run
    captured_at: StrictStr
    receipt_sha256: Digest

    @field_validator("captured_at")
    @classmethod
    def timestamp(cls, value):
        _time(value)
        return value


class _Privacy(_Evidence):
    gate: Literal["privacy"]
    private_bucket: StrictBool
    r2_dev_enabled: StrictBool
    public_custom_domain_count: Annotated[int, Field(strict=True, ge=0, le=32)]


class _LeastPrivilege(_Evidence):
    gate: Literal["least_privilege"]
    bucket_bindings: Annotated[list[Bucket], Field(min_length=1, max_length=8)]
    account_wide_access: StrictBool
    object_read: StrictBool
    object_write: StrictBool
    control_plane_write: StrictBool


class _SignedPut(_Evidence):
    gate: Literal["signed_put"]
    actual_signed_requests: StrictBool
    signed_headers: Annotated[list[Header], Field(min_length=1, max_length=16)]
    probe_size_bytes: Annotated[int, Field(strict=True, ge=1, le=MAX_MEDIA_BYTES)]
    probe_mime_type: Mime
    probe_sha256: Digest
    readback_sha256: Digest
    fresh_put_status: HTTPStatus
    repeat_put_status: HTTPStatus
    changed_length_status: HTTPStatus
    changed_type_status: HTTPStatus
    original_create_only_exercised: StrictBool
    probe_identity_sha256: Digest
    probe_disposition: Literal["retained", "confirmed_removed", "unknown"]
    probe_removal_receipt_sha256: Digest | None


class _BrowserCors(_Evidence):
    gate: Literal["browser_cors"]
    actual_browser_session: StrictBool
    request_origin: StrictStr
    allowed_origins: Annotated[list[StrictStr], Field(min_length=1, max_length=8)]
    allowed_methods: Annotated[list[Literal["GET", "HEAD", "PUT", "POST", "DELETE", "OPTIONS"]], Field(min_length=1, max_length=6)]
    allowed_headers: Annotated[list[Header], Field(min_length=1, max_length=16)]
    preflight_status: HTTPStatus
    put_response_visible: StrictBool
    get_response_visible: StrictBool
    foreign_origin_denied: StrictBool
    allow_credentials: StrictBool

    @field_validator("request_origin")
    @classmethod
    def origin(cls, value):
        return _origin(value)

    @field_validator("allowed_origins")
    @classmethod
    def origins(cls, values):
        return [_origin(value, wildcard=True) for value in values]


class _Host(_Evidence):
    gate: Literal["host_inspection"]
    platform: Literal["linux", "darwin", "windows"]
    python_minor: Literal["3.12", "3.13", "3.14"]
    inspected_mime_types: Annotated[list[Mime], Field(min_length=1, max_length=3)]
    image_bytes_verified: StrictBool
    video_bytes_verified: StrictBool
    ffprobe_available: StrictBool
    cpu_limit_seconds: Annotated[int, Field(strict=True, ge=15, le=15)]
    output_limit_bytes: Annotated[int, Field(strict=True, ge=64 * 1024, le=64 * 1024)]
    file_descriptor_limit: Annotated[int, Field(strict=True, ge=64, le=64)]
    address_space_limit_bytes: Annotated[int, Field(strict=True, ge=512 * 1024 * 1024, le=512 * 1024 * 1024)]
    inspection_timeout_seconds: Annotated[int, Field(strict=True, ge=1, le=30)]
    api_request_limit_bytes: Annotated[int, Field(strict=True, ge=1, le=MAX_MEDIA_BYTES)]
    api_metadata_request_size_bytes: Annotated[int, Field(strict=True, ge=1, le=MAX_JSON_BYTES)]
    api_metadata_request_sha256: Digest
    api_metadata_operation: Literal["initiate_upload", "complete_upload"]
    api_metadata_response_status: HTTPStatus
    resource_limits_exercised: StrictBool
    request_limits_exercised: StrictBool
    timeout_reaping_exercised: StrictBool


class _Accounting(_Evidence):
    gate: Literal["storage_accounting"]
    inventory_objects: Count
    inventory_bytes: Count
    ledger_reserved_bytes: Count
    unmanaged_objects: Count
    unknown_uploads: Count
    released_legacy_hazards: Count
    total_quota_bytes: Annotated[int, Field(strict=True, ge=1, le=10 * 1024**3)]
    actor_quota_bytes: Annotated[int, Field(strict=True, ge=1, le=1024**3)]
    ready_original_deletion_enabled: StrictBool
    quota_tracking_exercised: StrictBool
    retention_policy_sha256: Digest
    backup_restore_receipt_sha256: Digest
    backup_restore_exercised: StrictBool
    retained_probe_identity_sha256: Digest | None
    retained_probe_bytes: Count
    probe_actor_reserved_bytes: Count


class _Hosting(_Evidence):
    gate: Literal["hosting_profile"]
    profile_purpose: Literal["social_media_481"]
    operating_receipt_sha256: Digest
    owner_cost_review_sha256: Digest
    deployment_bound: StrictBool
    always_on_inspection_host: StrictBool
    capacity_bounds_reviewed: StrictBool
    egress_profile_reviewed: StrictBool


_Gate = Annotated[Union[_Privacy, _LeastPrivilege, _SignedPut, _BrowserCors, _Host, _Accounting, _Hosting], Field(discriminator="gate")]


class _Packet(_Model):
    schema_version: Annotated[int, Field(strict=True, ge=1, le=1)]
    scope: _Scope
    run_id: Run
    evidence_kind: Literal["operator_supplied", "synthetic"]
    evidence: Annotated[list[_Gate], Field(max_length=7)]


def _requirements(evidence, scope):
    """Checks assertions in the packet, not the observations they describe."""
    if isinstance(evidence, _Privacy):
        return evidence.private_bucket and not evidence.r2_dev_enabled and evidence.public_custom_domain_count == 0
    if isinstance(evidence, _LeastPrivilege):
        return (evidence.bucket_bindings == [scope.bucket] and not evidence.account_wide_access
                and evidence.object_read and evidence.object_write and not evidence.control_plane_write)
    if isinstance(evidence, _SignedPut):
        return (evidence.actual_signed_requests and evidence.original_create_only_exercised
                and {"host", "content-length", "content-type", "if-none-match"} <= set(evidence.signed_headers)
                and evidence.fresh_put_status == 200 and evidence.repeat_put_status == 412
                and evidence.changed_length_status in (400, 403) and evidence.changed_type_status == 403
                and evidence.probe_sha256 == evidence.readback_sha256
                and evidence.probe_mime_type in scope.required_mime_types
                and evidence.probe_size_bytes <= (MAX_MEDIA_BYTES if evidence.probe_mime_type == "video/mp4" else 10 * 1024 * 1024)
                and ((evidence.probe_disposition == "retained" and evidence.probe_removal_receipt_sha256 is None)
                     or (evidence.probe_disposition == "confirmed_removed" and evidence.probe_removal_receipt_sha256 is not None)))
    if isinstance(evidence, _BrowserCors):
        return (evidence.actual_browser_session and evidence.request_origin == scope.browser_origin
                and evidence.allowed_origins == [scope.browser_origin]
                and {"GET", "PUT"} <= set(evidence.allowed_methods) <= {"GET", "PUT", "HEAD"}
                and {"content-type", "if-none-match"} <= set(evidence.allowed_headers)
                and "*" not in evidence.allowed_headers and evidence.preflight_status in (200, 204)
                and evidence.put_response_visible and evidence.get_response_visible
                and evidence.foreign_origin_denied and not evidence.allow_credentials)
    if isinstance(evidence, _Host):
        return (evidence.platform == "linux" and evidence.python_minor == "3.12"
                and set(scope.required_mime_types) <= set(evidence.inspected_mime_types)
                and evidence.image_bytes_verified and evidence.resource_limits_exercised
                and evidence.request_limits_exercised and evidence.timeout_reaping_exercised
                and evidence.api_metadata_request_size_bytes <= evidence.api_request_limit_bytes
                and evidence.api_metadata_response_status == (201 if evidence.api_metadata_operation == "initiate_upload" else 200)
                and ("video/mp4" not in scope.required_mime_types or (evidence.ffprobe_available and evidence.video_bytes_verified)))
    if isinstance(evidence, _Accounting):
        return (evidence.inventory_objects <= evidence.inventory_bytes <= evidence.ledger_reserved_bytes <= evidence.total_quota_bytes
                and evidence.actor_quota_bytes <= evidence.total_quota_bytes
                and evidence.retained_probe_bytes <= evidence.inventory_bytes
                and evidence.retained_probe_bytes <= evidence.probe_actor_reserved_bytes <= evidence.actor_quota_bytes
                and evidence.probe_actor_reserved_bytes <= evidence.ledger_reserved_bytes
                and (evidence.inventory_objects == 0) == (evidence.inventory_bytes == 0)
                and not (evidence.unmanaged_objects or evidence.unknown_uploads or evidence.released_legacy_hazards)
                and not evidence.ready_original_deletion_enabled and evidence.quota_tracking_exercised
                and evidence.backup_restore_exercised)
    return (evidence.deployment_bound and evidence.always_on_inspection_host
            and evidence.capacity_bounds_reviewed and evidence.egress_profile_reviewed)


def _probe_accounting(accounting, signed_put):
    if not isinstance(signed_put, _SignedPut):
        return False
    if signed_put.probe_disposition == "retained":
        return (accounting.retained_probe_identity_sha256 == signed_put.probe_identity_sha256
                and accounting.retained_probe_bytes == signed_put.probe_size_bytes
                # This packet carries no independently established settlement
                # for reducing the upload's quarantine + final-copy envelope.
                and accounting.probe_actor_reserved_bytes >= 2 * signed_put.probe_size_bytes
                and accounting.inventory_objects >= 1)
    if signed_put.probe_disposition == "confirmed_removed":
        return (signed_put.probe_removal_receipt_sha256 is not None
                and accounting.retained_probe_identity_sha256 is None
                and accounting.retained_probe_bytes == 0)
    return False


def _report(status, reasons, *, gates=None, scope_hash=None, packet_hash=None):
    return {"schema_version": 1, "purpose": "social_media_490", "status": status,
        "validation_scope": "declared_evidence_only", "reason_codes": reasons,
        "scope_fingerprint": scope_hash, "packet_fingerprint": packet_hash,
        "gates": gates if gates is not None else [{"gate": gate, "status": "not_checked", "reason_codes": []} for gate in GATES],
        "evidence_authenticated": False, "live_acceptance": "not_run", "production_authorized": False,
        "publishing_authorized": False, "storage_enabled": False, "maintenance_authorized": False,
        "write_quiescence_proven": False, "ready_original_deletion_authorized": False}


def evaluate_packet(packet, *, expected_scope, as_of):
    """Return a safe offline report. Complete declarations permit review only.

    Neither supplied hashes, timestamps nor Boolean assertions authenticate an
    artifact or establish that any browser/server write has stopped.
    """
    try:
        _check(expected_scope)
        scope = _Scope.model_validate(expected_scope)
        current = _time(as_of)
        scope_hash = hashlib.sha256(_canonical(scope.model_dump())).hexdigest()
    except (ValueError, TypeError, RecursionError, OverflowError):
        return _report("UNVERIFIED_SUPPLIED_EVIDENCE", ["INVALID_REVIEW_SCOPE_OR_AS_OF"])
    if packet is None:
        return _report("MISSING_EVIDENCE", ["PACKET_REQUIRED"], scope_hash=scope_hash)
    try:
        _check(packet)
        parsed = _Packet.model_validate(packet)
        if len({item.gate for item in parsed.evidence}) != len(parsed.evidence):
            raise PacketError()
        packet_hash = hashlib.sha256(_canonical(packet)).hexdigest()
    except (ValueError, TypeError, RecursionError, OverflowError):
        return _report("UNVERIFIED_SUPPLIED_EVIDENCE", ["INVALID_PACKET"], scope_hash=scope_hash)
    if parsed.scope != scope:
        return _report("UNVERIFIED_SUPPLIED_EVIDENCE", ["PACKET_SCOPE_MISMATCH"], scope_hash=scope_hash, packet_hash=packet_hash)
    present = {item.gate: item for item in parsed.evidence}
    gates, missing, invalid = [], False, False
    for gate in GATES:
        item = present.get(gate)
        reasons = []
        if item is None:
            missing = True
            reasons.append("GATE_REQUIRED")
        else:
            if item.scope != scope or item.run_id != parsed.run_id:
                reasons.append("EVIDENCE_SCOPE_OR_RUN_MISMATCH")
            age = current - _time(item.captured_at)
            if age < timedelta(0) or age > MAX_EVIDENCE_AGE:
                reasons.append("EVIDENCE_STALE_OR_FUTURE")
            if not _requirements(item, scope):
                reasons.append("DECLARATION_REQUIREMENTS_NOT_MET")
            if isinstance(item, _Accounting) and not _probe_accounting(item, present.get("signed_put")):
                reasons.append("PROBE_DISPOSITION_OR_ACCOUNTING_MISMATCH")
            invalid |= bool(reasons)
        gates.append({"gate": gate, "status": "missing" if item is None else "declared_unverified" if reasons else "declared_checks_match", "reason_codes": reasons})
    if parsed.evidence_kind == "synthetic":
        invalid = True
    status = "MISSING_EVIDENCE" if missing else "UNVERIFIED_SUPPLIED_EVIDENCE" if invalid else "READY_FOR_OPERATOR_REVIEW"
    reasons = (["REQUIRED_GATES_MISSING"] if missing else []) + (["SUPPLIED_DECLARATIONS_UNVERIFIED"] if invalid else [])
    if parsed.evidence_kind == "synthetic":
        reasons.append("SYNTHETIC_EVIDENCE_ONLY")
    reasons.append("RECEIPTS_NOT_AUTHENTICATED")
    return _report(status, reasons, gates=gates, scope_hash=scope_hash, packet_hash=packet_hash)
