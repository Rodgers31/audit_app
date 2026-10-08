# Offline media evidence review (#490)

`social.media.acceptance` checks bounded **declarations** for the inspected
social-media workload. It reads no environment, files, clock, database or network.
The separate CLI reads only explicitly supplied regular JSON files. Neither
entrypoint probes storage, signs grants, starts maintenance or enables a runtime.

A supplied hash does not authenticate a receipt. A matching complete packet can
be `READY_FOR_OPERATOR_REVIEW`; every report still has
`validation_scope: declared_evidence_only`, `evidence_authenticated: false`,
`live_acceptance: not_run`, and false production, publishing, storage,
maintenance, write-quiescence and ready-original-deletion authorization fields.
Exit zero means the declarations satisfy the review schema, never acceptance
of the operations they describe. Marked synthetic packets stay unverified.

## Inputs and output

The public functions are `parse_json(raw)` and
`evaluate_packet(packet, *, expected_scope, as_of)`. `parse_json` accepts UTF-8
bytes/text, rejects duplicate keys and raises the fixed `PacketError` code
`MEDIA_ACCEPTANCE_INVALID_JSON`, without retaining decoder exceptions or their
raw input in its exception context. The evaluator accepts raw JSON-shaped objects
and returns a safe report for missing, malformed or mismatched inputs. It
revalidates every call, including direct Python calls; it does not trust a
previously parsed object. Reports contain gate names/reasons and fingerprints,
not raw evidence, object keys, URLs, credentials, subjects or DSNs.

The independently supplied `expected_scope` must contain exactly:

| Field | Declaration |
| --- | --- |
| `purpose` | `social_media_490` |
| `storage_endpoint` | Canonical `https://<32 lowercase hex account>.r2.cloudflarestorage.com`, without trailing slash |
| `bucket` | Exact private social bucket, 3–63 bounded bucket-name characters |
| `browser_origin` | Exact lowercase HTTPS origin, with no path/query/userinfo/fragment/wildcard |
| `host_id` | Intended host identity, a bounded identifier |
| `build_commit` | Exact 40-character lowercase Git hash |
| `config_sha256` | 64-character lowercase hash of the separately retained configuration declaration |
| `required_mime_types` | Unique JPEG/PNG slice, optionally including MP4 |

Scope is supplied separately; the CLI never copies its expected identity from
the packet. Each packet and each gate repeats that scope. The packet has
`schema_version: 1`, canonical UUID-shaped `run_id`, `evidence_kind`
(`operator_supplied` or `synthetic`) and an `evidence` list. Each evidence entry
has its own `gate`, `scope`, matching `run_id`, timezone-aware `captured_at`,
declared `receipt_sha256` and the gate-specific fields below. Retain the actual
artifacts separately for independent review; this tool does not read or verify
them. At most one entry per gate is accepted.

Review time is explicit: `as_of` is an ISO timestamp with seconds and timezone.
Every capture must fall within the preceding 24 hours, including both endpoints.
This is a declared-evidence freshness policy for review. It proves neither clock
accuracy nor the expiry, completion or fencing of a remote write.

## Independent gates

All fields are required; Booleans and integers are strict. Lists have bounded,
unique entries. No unknown fields or arbitrary explanatory text are accepted.

| Gate | Required declarations |
| --- | --- |
| `privacy` | `private_bucket: true`, `r2_dev_enabled: false`, `public_custom_domain_count: 0` |
| `least_privilege` | `bucket_bindings` contains only the expected bucket; `account_wide_access` and `control_plane_write` are false; `object_read` and `object_write` are true |
| `signed_put` | `actual_signed_requests` and `original_create_only_exercised` are true; `signed_headers` include host/content-length/content-type/if-none-match; bounded `probe_size_bytes`, allowed `probe_mime_type`, matching `probe_sha256`/`readback_sha256`; `probe_identity_sha256`, `probe_disposition` and nullable `probe_removal_receipt_sha256`; `fresh_put_status: 200`, `repeat_put_status: 412`, rejected `changed_length_status` (400/403) and `changed_type_status: 403` |
| `browser_cors` | `actual_browser_session: true`, exact `request_origin` and one exact `allowed_origins` entry; GET/PUT in `allowed_methods`, optional HEAD; content-type/if-none-match in `allowed_headers`, no wildcard; `preflight_status` 200/204; `put_response_visible`, `get_response_visible`, `foreign_origin_denied` true; `allow_credentials: false` |
| `host_inspection` | Intended Linux/Python 3.12 declarations; `inspected_mime_types` covers the scope; `image_bytes_verified`, `resource_limits_exercised`, `request_limits_exercised`, `timeout_reaping_exercised` true; MP4 additionally requires `ffprobe_available` and `video_bytes_verified`; child limits and separately measured API metadata fields below |
| `storage_accounting` | `inventory_objects`, `inventory_bytes`, `ledger_reserved_bytes`; `retained_probe_identity_sha256`, `retained_probe_bytes`, `probe_actor_reserved_bytes`; zero `unmanaged_objects`, `unknown_uploads`, `released_legacy_hazards`; `total_quota_bytes`, `actor_quota_bytes`; `ready_original_deletion_enabled: false`, `quota_tracking_exercised: true`; `retention_policy_sha256`, `backup_restore_receipt_sha256`, `backup_restore_exercised: true` |
| `hosting_profile` | `profile_purpose: social_media_481`, declared `operating_receipt_sha256` and `owner_cost_review_sha256`; `deployment_bound`, `always_on_inspection_host`, `capacity_bounds_reviewed`, `egress_profile_reviewed` true |

Declared child resource limits must match the current Linux inspector exactly:
`cpu_limit_seconds: 15`, `output_limit_bytes: 65536`,
`file_descriptor_limit: 64`, `address_space_limit_bytes: 536870912`.
The separate `inspection_timeout_seconds` is configurable from 1 through 30.
Values alone do not prove enforcement; review the retained executions.

The API receives metadata rather than the signed PUT body. Its
`api_request_limit_bytes` is positive and at most 50 MiB, and must cover the
separate `api_metadata_request_size_bytes` (1–128 KiB). Supply the metadata
request's `api_metadata_request_sha256`, `api_metadata_operation`
(`initiate_upload` or `complete_upload`) and `api_metadata_response_status`
(201 for initiation, 200 for completion). No size relationship with the R2 probe
is inferred. Actual host/request-profile suitability remains independently
unverified.

JPEG/PNG probe size cannot exceed 10 MiB; MP4 cannot exceed 50 MiB. Signed
header names cannot contain wildcards. Positive media object count cannot exceed
its byte count. Inventory bytes cannot exceed declared reserved bytes or total
quota; actor quota cannot exceed total quota. Object-count/byte emptiness must
agree. The probe actor's reserved bytes must fit both its actor quota and the
global ledger, including after declared probe removal.

A `retained` probe has no removal receipt. Its identity must match
`retained_probe_identity_sha256`, its size must equal `retained_probe_bytes`, and
the inventory must contain at least one object. Those bytes must fit the
inventory and the probe actor's reservation. A `confirmed_removed` declaration
needs its own removal receipt hash, null retained identity and zero retained
probe bytes. An `unknown` disposition stays unverified. These checks only
compare supplied assertions: a removal hash proves neither deletion nor write
quiescence, and authorizes no reservation release. The evaluator restores no
missing legacy accounting. Zero declared unknowns do not prove quiescence, and
the production verifier remains unsupported.

Results distinguish `MISSING_EVIDENCE` (required packet/gate absent),
`UNVERIFIED_SUPPLIED_EVIDENCE` (malformed, stale, mixed, synthetic or unsafe
declarations), and `READY_FOR_OPERATOR_REVIEW`. Gate statuses explicitly refer
to declarations. The fingerprints identify submitted JSON; they provide no
signature, independent authentication or operator approval.

## CLI

From `backend`, with the existing environment:

```sh
python -B -m scripts.social_media_acceptance --help
python -B -m scripts.social_media_acceptance \
  --scope <independent-scope.json> --packet <declared-evidence.json> \
  --as-of 2026-10-08T12:00:00Z
```

Help/default/error paths do not load configuration or start live clients. Default
invocation reports missing explicit scope/time and exits 2. Refused input prints
a fixed code, without error details or input paths. Only review-ready declarations
exit 0. Files must be regular, not symlinks/FIFOs/devices, and ≤128 KiB. JSON is
also bounded to depth 12, 4,096 values, 32 list entries, 64 object keys and
2,048 characters per string; nonfinite/floating values, duplicate keys and
unknown schema fields are rejected. No output file is written automatically.
CLI arguments are limited to 16 strings of at most 2,048 characters, without
control characters.

## Operational acceptance still required

The existing source-evidence R2 receipt covers a different workload and cannot
replace social bucket policy, signed-upload behavior or browser CORS evidence.
Local signer tests and Python OPTIONS requests cannot establish actual browser
behavior. Local macOS inspection does not establish intended Linux/Python 3.12
availability/resource enforcement. Storage/private-policy and least-privilege
claims need review against independently obtained authorized artifacts.

Actual tests need their separate bounded authorization and capture plan. Account
for accepted or uncertain probe writes; do not delete or release reservations on
the basis of a timeout, age, HEAD or prior DELETE. Preserve originals, provenance
and historical references. A separately reviewed write-drain mechanism, actual
inventory/reconciliation, backup/retention and #481 hosting/egress receipts,
followed by an explicit owner enablement decision, remain necessary. This tool
adds no receipt trust, production verification or quiescence authority.

## Executed verification

The authored `test_media_acceptance.py` suite passed 170 cases: scoped positive
declarations, marked synthetic and missing gates, unrelated source receipts,
stale/mixed identities, strict types/limits, malformed/duplicate JSON, secret
redaction, regular-file bounds and direct/CLI invocation. Its fresh-process
probe forbids socket connections, subprocess creation, engine creation,
dotenv loading and boto3 client construction during import/help/default paths.
Three self-review contradictions were observed red, then repaired: wildcard
signed headers, an image probe above the image ceiling and more nonempty media
objects than bytes. Independent review retained ten observed-red cases for
incorrect child limits, decoder exception privacy, and probe inventory/quota/API
metadata consistency. Further observed-red regressions cover malformed direct
CLI arguments and an actor reservation exceeding the global ledger. Independent
re-execution rejected 239 hostile declarations, 12 parser inputs and six CLI
inputs while preserving three positive controls. The configurable one-second
inspection timeout remains valid.

Fixtures are deliberately invented, and no real storage/host acceptance is
claimed. The assigned worktree's existing libraries were reused; no deployment,
configuration, live provider, database or dependency change occurred.
