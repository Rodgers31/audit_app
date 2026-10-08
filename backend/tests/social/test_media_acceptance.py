"""Declared evidence only. Synthetic inputs and local processes; no providers."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from social.media.acceptance import GATES, MAX_JSON_BYTES, PacketError, evaluate_packet, parse_json
from scripts import social_media_acceptance as cli

AS_OF = "2026-10-08T12:00:00Z"
CAPTURED = "2026-10-08T11:30:00Z"
RUN = "de8b4ec2-5d11-4555-8f3e-7dcd8c86a2fe"
SECRET = "private-secret-must-never-appear"


@pytest.fixture
def scope():
    return {"purpose": "social_media_490", "storage_endpoint": "https://" + "a" * 32 + ".r2.cloudflarestorage.com",
        "bucket": "social-media-fixture", "browser_origin": "https://admin.example.org", "host_id": "intended-linux-fixture",
        "build_commit": "b" * 40, "config_sha256": "c" * 64, "required_mime_types": ["image/jpeg", "image/png"]}


@pytest.fixture
def packet(scope):
    # These invented hashes/declarations validate schema, never real acceptance.
    values = {
        "privacy": {"private_bucket": True, "r2_dev_enabled": False, "public_custom_domain_count": 0},
        "least_privilege": {"bucket_bindings": [scope["bucket"]], "account_wide_access": False,
            "object_read": True, "object_write": True, "control_plane_write": False},
        "signed_put": {"actual_signed_requests": True, "signed_headers": ["host", "content-length", "content-type", "if-none-match"],
            "probe_size_bytes": 64, "probe_mime_type": "image/png", "probe_sha256": "d" * 64,
            "readback_sha256": "d" * 64, "fresh_put_status": 200, "repeat_put_status": 412,
            "changed_length_status": 403, "changed_type_status": 403, "original_create_only_exercised": True,
            "probe_identity_sha256": "a" * 64, "probe_disposition": "retained", "probe_removal_receipt_sha256": None},
        "browser_cors": {"actual_browser_session": True, "request_origin": scope["browser_origin"],
            "allowed_origins": [scope["browser_origin"]], "allowed_methods": ["GET", "PUT", "HEAD"],
            "allowed_headers": ["content-type", "if-none-match"], "preflight_status": 204,
            "put_response_visible": True, "get_response_visible": True, "foreign_origin_denied": True, "allow_credentials": False},
        "host_inspection": {"platform": "linux", "python_minor": "3.12", "inspected_mime_types": ["image/jpeg", "image/png"],
            "image_bytes_verified": True, "video_bytes_verified": False, "ffprobe_available": False,
            "cpu_limit_seconds": 15, "output_limit_bytes": 65536, "file_descriptor_limit": 64,
            "address_space_limit_bytes": 512 * 1024 * 1024, "inspection_timeout_seconds": 20,
            "api_request_limit_bytes": 65536, "api_metadata_request_size_bytes": 128,
            "api_metadata_request_sha256": "b" * 64, "api_metadata_operation": "initiate_upload",
            "api_metadata_response_status": 201, "resource_limits_exercised": True,
            "request_limits_exercised": True, "timeout_reaping_exercised": True},
        "storage_accounting": {"inventory_objects": 2, "inventory_bytes": 256, "ledger_reserved_bytes": 512,
            "unmanaged_objects": 0, "unknown_uploads": 0, "released_legacy_hazards": 0,
            "total_quota_bytes": 2 * 1024**3, "actor_quota_bytes": 200 * 1024**2,
            "ready_original_deletion_enabled": False, "quota_tracking_exercised": True,
            "retention_policy_sha256": "e" * 64, "backup_restore_receipt_sha256": "f" * 64, "backup_restore_exercised": True,
            "retained_probe_identity_sha256": "a" * 64, "retained_probe_bytes": 64, "probe_actor_reserved_bytes": 128},
        "hosting_profile": {"profile_purpose": "social_media_481", "operating_receipt_sha256": "1" * 64,
            "owner_cost_review_sha256": "2" * 64, "deployment_bound": True, "always_on_inspection_host": True,
            "capacity_bounds_reviewed": True, "egress_profile_reviewed": True},
    }
    return {"schema_version": 1, "scope": deepcopy(scope), "run_id": RUN, "evidence_kind": "operator_supplied",
        "evidence": [{"gate": gate, "scope": deepcopy(scope), "run_id": RUN,
            "captured_at": CAPTURED, "receipt_sha256": str(index + 3) * 64, **values[gate]} for index, gate in enumerate(GATES)]}


def evaluate(value, scope, as_of=AS_OF):
    result = evaluate_packet(value, expected_scope=scope, as_of=as_of)
    assert result["validation_scope"] == "declared_evidence_only"
    assert result["live_acceptance"] == "not_run"
    for key in ("evidence_authenticated", "production_authorized", "publishing_authorized", "storage_enabled",
            "maintenance_authorized", "write_quiescence_proven", "ready_original_deletion_authorized"):
        assert result[key] is False
    return result


def gate(packet, name):
    return next(item for item in packet["evidence"] if item["gate"] == name)


def test_matching_declared_packet_only_becomes_ready_for_operator_review(packet, scope):
    before = deepcopy(packet)
    result = evaluate(packet, scope)
    assert result["status"] == "READY_FOR_OPERATOR_REVIEW"
    assert [item["status"] for item in result["gates"]] == ["declared_checks_match"] * 7
    assert result["reason_codes"] == ["RECEIPTS_NOT_AUTHENTICATED"]
    assert len(result["scope_fingerprint"]) == len(result["packet_fingerprint"]) == 64
    assert packet == before
    assert scope["browser_origin"] not in json.dumps(result)


def test_synthetic_claims_and_arbitrary_hashes_cannot_accept_real_evidence(packet, scope):
    packet["evidence_kind"] = "synthetic"
    result = evaluate(packet, scope)
    assert result["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"
    assert "SYNTHETIC_EVIDENCE_ONLY" in result["reason_codes"]
    # Hashes are declarations, including a superficially valid invented digest.
    packet["evidence_kind"] = "operator_supplied"
    gate(packet, "privacy")["receipt_sha256"] = "0" * 64
    assert evaluate(packet, scope)["evidence_authenticated"] is False


@pytest.mark.parametrize("missing", GATES)
def test_every_independent_gate_is_required(packet, scope, missing):
    packet["evidence"] = [item for item in packet["evidence"] if item["gate"] != missing]
    result = evaluate(packet, scope)
    assert result["status"] == "MISSING_EVIDENCE"
    assert next(item for item in result["gates"] if item["gate"] == missing)["status"] == "missing"


def test_missing_and_empty_are_truthful(packet, scope):
    assert evaluate(None, scope)["status"] == "MISSING_EVIDENCE"
    packet["evidence"] = []
    assert evaluate(packet, scope)["status"] == "MISSING_EVIDENCE"
    assert evaluate({}, scope)["reason_codes"] == ["INVALID_PACKET"]


@pytest.mark.parametrize("field,value", [
    ("purpose", "private_source_receipts_137"), ("storage_endpoint", "https://" + "d" * 32 + ".r2.cloudflarestorage.com"),
    ("bucket", "other-private-bucket"), ("browser_origin", "https://other.example.org"),
    ("host_id", "other-linux-host"), ("build_commit", "e" * 40), ("config_sha256", "f" * 64),
    ("required_mime_types", ["image/jpeg", "image/png", "video/mp4"]),
])
def test_top_level_scope_is_independently_bound(packet, scope, field, value):
    packet["scope"][field] = value
    assert evaluate(packet, scope)["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"


@pytest.mark.parametrize("scheme", ["HTTPS", "hTtPs"])
def test_browser_origin_requires_an_exact_lowercase_scheme_before_url_parsing(packet, scope, scheme):
    # Keep all declarations equal so this checks the raw scheme, not a mismatch.
    scope["browser_origin"] = scheme + scope["browser_origin"][5:]
    packet["scope"] = deepcopy(scope)
    for item in packet["evidence"]: item["scope"] = deepcopy(scope)
    gate(packet, "browser_cors").update(request_origin=scope["browser_origin"], allowed_origins=[scope["browser_origin"]])
    result = evaluate(packet, scope)
    assert result["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"
    assert result["reason_codes"] == ["INVALID_REVIEW_SCOPE_OR_AS_OF"]


@pytest.mark.parametrize("origin", [
    "https://admin.example.org?", "https://admin.example.org#", "https://admin.example.org?#",
    "https://admin.example.org:443", "https://127.1", "https://2130706433", "https://0x7f000001",
    "https://0177.0.0.1", "https://127.000.000.001", "https://08.0.0.1", "https://1.2.3.256",
    "https://admin.example.123", "https://admin.example.0x10", "https://admin.example.0x",
])
def test_observed_red_origin_must_equal_literal_browser_serialization(packet, scope, origin):
    scope["browser_origin"] = origin
    packet["scope"] = deepcopy(scope)
    for item in packet["evidence"]: item["scope"] = deepcopy(scope)
    gate(packet, "browser_cors").update(request_origin=origin, allowed_origins=[origin])
    assert evaluate(packet, scope)["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"


@pytest.mark.parametrize("origin", ["https://admin.example.org", "https://admin.example.org:8443",
    "https://127.0.0.1", "https://127.0.0.1:8443"])
def test_canonical_dns_and_ipv4_origins_remain_reviewable(packet, scope, origin):
    scope["browser_origin"] = origin
    packet["scope"] = deepcopy(scope)
    for item in packet["evidence"]: item["scope"] = deepcopy(scope)
    gate(packet, "browser_cors").update(request_origin=origin, allowed_origins=[origin])
    assert evaluate(packet, scope)["status"] == "READY_FOR_OPERATOR_REVIEW"


@pytest.mark.parametrize("field,value", [
    ("bucket", "other-private-bucket"), ("browser_origin", "https://other.example.org"),
    ("host_id", "other-host"), ("build_commit", "e" * 40), ("config_sha256", "f" * 64),
])
def test_a_gate_from_a_different_scope_cannot_be_borrowed(packet, scope, field, value):
    gate(packet, "browser_cors")["scope"][field] = value
    result = evaluate(packet, scope)
    assert result["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"
    assert "EVIDENCE_SCOPE_OR_RUN_MISMATCH" in next(item for item in result["gates"] if item["gate"] == "browser_cors")["reason_codes"]


@pytest.mark.parametrize("captured", ["2026-10-07T11:59:59Z", "2026-10-08T12:00:01Z"])
def test_stale_and_future_evidence_require_fresh_review(packet, scope, captured):
    gate(packet, "privacy")["captured_at"] = captured
    assert evaluate(packet, scope)["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"


def test_mixed_run_ids_are_not_one_packet(packet, scope):
    gate(packet, "privacy")["run_id"] = "00000000-0000-0000-0000-000000000000"
    assert evaluate(packet, scope)["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"


@pytest.mark.parametrize("name,field,value", [
    ("privacy", "private_bucket", False), ("privacy", "r2_dev_enabled", True), ("privacy", "public_custom_domain_count", 1),
    ("least_privilege", "bucket_bindings", ["social-media-fixture", "other-bucket"]),
    ("least_privilege", "account_wide_access", True), ("least_privilege", "object_read", False),
    ("least_privilege", "object_write", False), ("least_privilege", "control_plane_write", True),
    ("signed_put", "actual_signed_requests", False), ("signed_put", "signed_headers", ["host", "content-type", "if-none-match"]),
    ("signed_put", "fresh_put_status", 204), ("signed_put", "repeat_put_status", 200),
    ("signed_put", "changed_length_status", 200), ("signed_put", "changed_type_status", 200),
    ("signed_put", "readback_sha256", "0" * 64), ("signed_put", "original_create_only_exercised", False),
    ("browser_cors", "actual_browser_session", False), ("browser_cors", "allowed_origins", ["*"]),
    ("browser_cors", "allowed_origins", ["https://other.example.org"]), ("browser_cors", "request_origin", "https://other.example.org"),
    ("browser_cors", "allowed_methods", ["PUT"]), ("browser_cors", "allowed_methods", ["GET", "PUT", "DELETE"]),
    ("browser_cors", "allowed_headers", ["content-type", "*"]), ("browser_cors", "allowed_headers", ["content-type"]),
    ("browser_cors", "preflight_status", 403), ("browser_cors", "put_response_visible", False),
    ("browser_cors", "get_response_visible", False), ("browser_cors", "foreign_origin_denied", False),
    ("browser_cors", "allow_credentials", True),
    ("host_inspection", "platform", "darwin"), ("host_inspection", "python_minor", "3.13"),
    ("host_inspection", "inspected_mime_types", ["image/png"]), ("host_inspection", "image_bytes_verified", False),
    ("host_inspection", "resource_limits_exercised", False), ("host_inspection", "request_limits_exercised", False),
    ("host_inspection", "timeout_reaping_exercised", False),
    ("storage_accounting", "inventory_bytes", 1024), ("storage_accounting", "ledger_reserved_bytes", 3 * 1024**3),
    ("storage_accounting", "unmanaged_objects", 1), ("storage_accounting", "unknown_uploads", 1),
    ("storage_accounting", "released_legacy_hazards", 1), ("storage_accounting", "inventory_objects", 0),
    ("storage_accounting", "actor_quota_bytes", 1024**3), ("storage_accounting", "total_quota_bytes", 512),
    ("storage_accounting", "ready_original_deletion_enabled", True), ("storage_accounting", "quota_tracking_exercised", False),
    ("storage_accounting", "backup_restore_exercised", False),
    ("hosting_profile", "deployment_bound", False), ("hosting_profile", "always_on_inspection_host", False),
    ("hosting_profile", "capacity_bounds_reviewed", False), ("hosting_profile", "egress_profile_reviewed", False),
])
def test_unsafe_or_unmeasured_gate_stays_unverified(packet, scope, name, field, value):
    gate(packet, name)[field] = value
    # A lower total quota also exercises actor > total; otherwise 1GiB is valid.
    if field == "actor_quota_bytes": gate(packet, name)["total_quota_bytes"] = 512 * 1024**2
    assert evaluate(packet, scope)["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"


def test_optional_video_requires_actual_host_byte_inspection(packet, scope):
    scope["required_mime_types"].append("video/mp4")
    packet["scope"] = deepcopy(scope)
    for item in packet["evidence"]: item["scope"] = deepcopy(scope)
    host = gate(packet, "host_inspection")
    assert evaluate(packet, scope)["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"
    host.update(inspected_mime_types=scope["required_mime_types"], ffprobe_available=True, video_bytes_verified=True)
    assert evaluate(packet, scope)["status"] == "READY_FOR_OPERATOR_REVIEW"


@pytest.mark.parametrize("change", ["wildcard_signed_header", "image_above_ceiling", "impossible_object_count"])
def test_contradictory_declared_storage_measurements_are_refused(packet, scope, change):
    if change == "wildcard_signed_header": gate(packet, "signed_put")["signed_headers"].append("*")
    if change == "image_above_ceiling": gate(packet, "signed_put")["probe_size_bytes"] = 10 * 1024**2 + 1
    if change == "impossible_object_count": gate(packet, "storage_accounting")["inventory_objects"] = 257
    assert evaluate(packet, scope)["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"


@pytest.mark.parametrize("field", ["cpu_limit_seconds", "output_limit_bytes", "file_descriptor_limit", "address_space_limit_bytes"])
def test_host_child_limits_match_the_actual_linux_inspector(packet, scope, field):
    gate(packet, "host_inspection")[field] = 1
    assert evaluate(packet, scope)["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"


@pytest.mark.parametrize("raw", [b'{"token":"' + SECRET.encode() + b'"', b'\xff' + SECRET.encode()])
def test_parser_exception_does_not_retain_decoder_context(raw):
    with pytest.raises(PacketError) as caught: parse_json(raw)
    assert caught.value.__context__ is None and caught.value.__cause__ is None


@pytest.mark.parametrize("value", [0, 1])
def test_accounting_cannot_omit_or_undercount_a_retained_probe(packet, scope, value):
    gate(packet, "storage_accounting").update(inventory_objects=value, inventory_bytes=value, ledger_reserved_bytes=value)
    assert evaluate(packet, scope)["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"


def test_a_retained_probe_must_fit_both_declared_quotas(packet, scope):
    gate(packet, "storage_accounting").update(inventory_objects=1, inventory_bytes=1, ledger_reserved_bytes=1,
        actor_quota_bytes=1, total_quota_bytes=1)
    assert evaluate(packet, scope)["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"


def test_global_ledger_covers_probe_actor_reservation_subset(packet, scope):
    gate(packet, "storage_accounting")["probe_actor_reserved_bytes"] = 513
    assert evaluate(packet, scope)["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"


@pytest.mark.parametrize("reserved", [64, 127])
def test_retained_probe_preserves_capacity_for_quarantine_and_final_copies(packet, scope, reserved):
    # A 64-byte retained upload needs 128 bytes even when only one copy is
    # currently inventoried. Inventory/actor/global consistency alone is weaker.
    gate(packet, "storage_accounting").update(inventory_objects=1, inventory_bytes=64,
        ledger_reserved_bytes=reserved, probe_actor_reserved_bytes=reserved)
    assert evaluate(packet, scope)["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"


def test_retained_probe_two_copy_reservation_boundary_allows_declared_review_only(packet, scope):
    gate(packet, "storage_accounting").update(inventory_objects=1, inventory_bytes=64,
        ledger_reserved_bytes=128, probe_actor_reserved_bytes=128, actor_quota_bytes=128, total_quota_bytes=128)
    assert evaluate(packet, scope)["status"] == "READY_FOR_OPERATOR_REVIEW"


def test_api_metadata_request_measurement_must_fit_its_own_limit(packet, scope):
    gate(packet, "host_inspection")["api_request_limit_bytes"] = 1
    assert evaluate(packet, scope)["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"


def test_confirmed_removed_probe_has_separate_declared_receipt_and_zero_retained_accounting(packet, scope):
    gate(packet, "signed_put").update(probe_disposition="confirmed_removed", probe_removal_receipt_sha256="c" * 64)
    gate(packet, "storage_accounting").update(inventory_objects=0, inventory_bytes=0, ledger_reserved_bytes=0,
        retained_probe_identity_sha256=None, retained_probe_bytes=0, probe_actor_reserved_bytes=0)
    result = evaluate(packet, scope)
    assert result["status"] == "READY_FOR_OPERATOR_REVIEW" and result["write_quiescence_proven"] is False
    gate(packet, "signed_put")["probe_removal_receipt_sha256"] = None
    assert evaluate(packet, scope)["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"


@pytest.mark.parametrize("name,field,value", [
    ("signed_put", "probe_disposition", "unknown"), ("signed_put", "probe_identity_sha256", "e" * 64),
    ("signed_put", "probe_removal_receipt_sha256", "c" * 64),
    ("storage_accounting", "retained_probe_identity_sha256", None),
    ("storage_accounting", "retained_probe_identity_sha256", "e" * 64),
    ("storage_accounting", "retained_probe_bytes", 0), ("storage_accounting", "retained_probe_bytes", 63),
    ("storage_accounting", "retained_probe_bytes", 65), ("storage_accounting", "probe_actor_reserved_bytes", 0),
    ("host_inspection", "api_metadata_request_size_bytes", 65537),
    ("host_inspection", "api_metadata_response_status", 200),
])
def test_probe_and_api_metadata_declarations_must_be_consistent(packet, scope, name, field, value):
    gate(packet, name)[field] = value
    assert evaluate(packet, scope)["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"


def test_configurable_timeout_and_api_metadata_limit_are_independent_of_storage_probe(packet, scope):
    gate(packet, "host_inspection").update(inspection_timeout_seconds=1, api_request_limit_bytes=128)
    assert evaluate(packet, scope)["status"] == "READY_FOR_OPERATOR_REVIEW"
    gate(packet, "host_inspection").update(api_metadata_operation="complete_upload", api_metadata_response_status=200)
    assert evaluate(packet, scope)["status"] == "READY_FOR_OPERATOR_REVIEW"


@pytest.mark.parametrize("value", [None, False, True, 0, 1, "garbage", [], [1], float("nan"), float("inf")])
def test_direct_api_wrong_shapes_are_bounded_and_safe(value, scope):
    assert evaluate(value, scope)["status"] != "READY_FOR_OPERATOR_REVIEW"


@pytest.mark.parametrize("as_of", [None, True, 1, datetime(2026, 10, 8, tzinfo=timezone.utc), "2026-10-08", "2026-10-08T12:00:00",
    "2026-02-30T12:00:00Z", "2026-10-08T24:00:00Z", "2026-10-08T12:00:00+14:01", "2026-10-08T12:00:00Z\n"])
def test_explicit_real_timestamp_is_required(packet, scope, as_of):
    assert evaluate(packet, scope, as_of)["reason_codes"] == ["INVALID_REVIEW_SCOPE_OR_AS_OF"]


@pytest.mark.parametrize("value", [True, False, "64", 64.0, -1, 0, float("nan"), float("inf"), 50 * 1024**2 + 1])
def test_probe_lengths_are_strict_and_bounded(packet, scope, value):
    gate(packet, "signed_put")["probe_size_bytes"] = value
    assert evaluate(packet, scope)["reason_codes"] == ["INVALID_PACKET"]


@pytest.mark.parametrize("name,field", [("privacy", "public_custom_domain_count"), ("signed_put", "fresh_put_status"),
    ("host_inspection", "cpu_limit_seconds"), ("storage_accounting", "inventory_bytes")])
def test_booleans_cannot_be_integers(packet, scope, name, field):
    gate(packet, name)[field] = True
    assert evaluate(packet, scope)["reason_codes"] == ["INVALID_PACKET"]


def test_duplicate_gates_and_list_entries_are_rejected(packet, scope):
    packet["evidence"][-1] = deepcopy(packet["evidence"][0])
    assert evaluate(packet, scope)["reason_codes"] == ["INVALID_PACKET"]
    packet["evidence"] = packet["evidence"][:-1]
    gate(packet, "signed_put")["signed_headers"].append("host")
    assert evaluate(packet, scope)["reason_codes"] == ["INVALID_PACKET"]


@pytest.mark.parametrize("raw", [b"", b"[]", b"null", b'{"x":1,"x":2}', b'{"x":{"a":1,"a":2}}', b'{"x":NaN}',
    b'{"x":Infinity}', b'{"x":1.2}', b'\xff', '{"x":"' + SECRET + '"', b'{"x":1}'.decode().encode('utf-16'),
    " " * (MAX_JSON_BYTES + 1), '{"x":"' + "a" * 2049 + '"}', '{"x":' + "[" * 20 + "0" + "]" * 20 + "}"])
def test_json_decoder_rejects_bad_encoding_duplicates_and_bounds_without_input_echo(raw):
    with pytest.raises(PacketError) as caught:
        parse_json(raw)
    assert str(caught.value) == "MEDIA_ACCEPTANCE_INVALID_JSON"
    assert SECRET not in repr(caught.value)


def test_direct_cycles_and_unknown_secret_fields_do_not_leak(packet, scope):
    cyclic = {}; cyclic["x"] = cyclic
    assert evaluate(cyclic, scope)["reason_codes"] == ["INVALID_PACKET"]
    packet["access_key"] = SECRET
    result = evaluate(packet, scope)
    assert result["reason_codes"] == ["INVALID_PACKET"] and SECRET not in json.dumps(result)


def test_source_storage_acceptance_is_not_social_workload_evidence(scope):
    source = {"status": "PASS", "scope": "bounded source storage/recovery/hosted producer acceptance", "evidence": []}
    assert evaluate(source, scope)["reason_codes"] == ["INVALID_PACKET"]


def test_cli_default_and_errors_are_safe_without_implicit_inputs(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_read", lambda _: pytest.fail("Default/error path read a file"))
    monkeypatch.setenv("SOCIAL_MEDIA_ACCESS_KEY", SECRET)
    assert cli.main([]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "MISSING_EVIDENCE" and result["storage_enabled"] is False
    assert cli.main(["--unknown-" + SECRET, SECRET]) == 2
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err
    assert json.loads(output.out)["reason_codes"] == ["MEDIA_ACCEPTANCE_INPUT_REFUSED"]


@pytest.mark.parametrize("argv", [[{"secret": SECRET}], [object()], [None], [1], [True], "invalid argv", ["a" * 2049]])
def test_direct_cli_argument_shapes_are_safe(argv, capsys):
    assert cli.main(argv) == 2
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err
    assert json.loads(output.out)["reason_codes"] == ["MEDIA_ACCEPTANCE_INPUT_REFUSED"]


def test_cli_positive_and_invalid_input_only_print_declared_review(packet, scope, tmp_path, capsys):
    source = tmp_path / "packet.json"; scope_file = tmp_path / "scope.json"
    source.write_text(json.dumps(packet)); scope_file.write_text(json.dumps(scope))
    args = ["--packet", str(source), "--scope", str(scope_file), "--as-of", AS_OF]
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "READY_FOR_OPERATOR_REVIEW" and result["production_authorized"] is False
    source.write_text('{"x":"' + SECRET)
    assert cli.main(args) == 2
    assert SECRET not in capsys.readouterr().out


@pytest.mark.parametrize("origin", ["https://admin.example.org?", "https://admin.example.org#",
    "https://admin.example.org:443", "https://127.1"])
def test_observed_red_cli_refuses_noncanonical_browser_origin(packet, scope, origin, tmp_path, capsys):
    scope["browser_origin"] = origin
    packet["scope"] = deepcopy(scope)
    for item in packet["evidence"]: item["scope"] = deepcopy(scope)
    gate(packet, "browser_cors").update(request_origin=origin, allowed_origins=[origin])
    source = tmp_path / "packet.json"; scope_file = tmp_path / "scope.json"
    source.write_text(json.dumps(packet)); scope_file.write_text(json.dumps(scope))
    assert cli.main(["--packet", str(source), "--scope", str(scope_file), "--as-of", AS_OF]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "UNVERIFIED_SUPPLIED_EVIDENCE"
    assert result["production_authorized"] is False


@pytest.mark.parametrize("kind", ["missing", "directory", "oversized", "symlink", "fifo"])
def test_cli_refuses_unbounded_or_nonregular_input(kind, tmp_path, capsys):
    source = tmp_path / "input"
    if kind == "directory": source.mkdir()
    if kind == "oversized": source.write_bytes(b" " * (MAX_JSON_BYTES + 1))
    if kind == "symlink": source.symlink_to(tmp_path / SECRET)
    if kind == "fifo": os.mkfifo(source)
    assert cli.main(["--scope", str(source), "--as-of", AS_OF]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["reason_codes"] == ["MEDIA_ACCEPTANCE_INPUT_REFUSED"]


def test_cli_help_import_and_default_have_no_provider_or_runtime_side_effects():
    backend = Path(__file__).resolve().parents[2]
    script = '''
import socket, subprocess, sqlalchemy, dotenv, boto3
def forbidden(*args, **kwargs): raise RuntimeError('external side effect forbidden')
socket.socket.connect = forbidden
subprocess.Popen = forbidden
sqlalchemy.create_engine = forbidden
dotenv.load_dotenv = forbidden
boto3.client = forbidden
from scripts.social_media_acceptance import main
assert main([]) == 2
try: main(['--help'])
except SystemExit as error: assert error.code == 0
else: raise AssertionError('help did not exit')
'''
    result = subprocess.run([sys.executable, "-B", "-c", script], cwd=backend,
        env={**os.environ, "PYTHONPATH": str(backend), "SOCIAL_MEDIA_ACCESS_KEY": SECRET},
        capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert SECRET not in result.stdout + result.stderr
    assert "no receipts are authenticated" in " ".join(result.stdout.split())
