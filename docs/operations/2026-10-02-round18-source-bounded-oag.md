# Explicit five-source OAG execution

This implements the execution-scope prerequisite for #234/#230. Neither issue
is closed by local verification. Actions remains OFF; this document grants no
production ingestion, workflow dispatch, refresh or configuration authorization.

## Command and identity

From the `backend` directory of the reviewed checkout, propose:

```sh
python -m seeding.cli seed --domain audits \
  --audits-source-manifest ../docs/operations/2026-10-01-round11-oag-catchup/manifest.json \
  --no-dry-run
```

The interpreter, checkout commit, working directory and resolved runtime must
be frozen in the later approved release receipt. This uses the existing CLI,
handler, fetcher, reconciliation and loader. The scheduled default and manual
`domain=audits` workflow do not supply this flag and retain their existing scope.
Do not substitute that workflow for this bounded command.

Only the exact bytes of the [reviewed manifest](2026-10-01-round11-oag-catchup/manifest.json)
are accepted: SHA256
`9388815ee8233d727558a2b47aef6bf3c4c6b6f1565dac22a4c8c10bbe9b6277`.
The five editions are FY2023/24 assemblies, FY2022/23 executives and assemblies,
and FY2021/22 executives and assemblies. Whitespace edits, arbitrary URL lists,
duplicates, empty scope and other packets are rejected before an ingestion job
is written. The flag requires only `--domain audits`, without `--all`.
There is no configurable digest override. Changed evidence requires review.

The handler independently validates the packet. It offers only those five
URLs and bypasses broad discovery, known/registered retries, national reports,
the three already-current volumes, FY2020/21 and the Homa Bay standalone PDF.
Existing selected records must retain Kenya, publisher, document type, known
MD5, year/institution/listing association and any recorded artifact identity.
Returned PDF bytes must match both manifest digests before extraction.
Direct registration and loading enforce the same boundary. Present malformed
artifact bindings, including JSON null, are refused; absent legacy bindings
remain absent. Loading applies the unchanged publication predicate only to the
selected document's audits, including withholding and retired-fixture buckets.

## Outcomes and recovery

Job metadata records the manifest digest, selected identities and attempted,
processed, already-current, deferred and refused URLs. Inventory is explicitly
`reviewed_retained_manifest_not_live_discovery`, with `whole_world_coverage=false`.
Do not interpret retained `listed_at` context as a fresh listing observation.

Normal start/download/domain/total budgets remain in force. Selected
registration and completed volumes are committed individually. A timeout or
later refusal can leave earlier commits; the scope receipt survives the CLI's
failure handling. Deferred/refused scope returns a nonzero CLI status. Inspect
the receipt before proposing a resumed command. Resume uses the same reviewed
manifest and preserves cached extraction evidence. Do not clear MD5/evidence,
approve retirements, broaden the scope or perform inverse deletion to force
success.

## Local evidence and live acceptance

Round18 S04's evidence bank contains behavioral baseline red, fixed green,
direct-consumer red/green, timeout/resume and independent adversarial receipts.
The final focused selection passed 297 tests with zero failures/skips; the
independent review passed 127. Three dependency warnings were retained.
Application-engine connections and provider HTTP were blocked in these tests.

An owned PostgreSQL 17.11 clone exercised the real CLI/fetcher/parser/
reconciliation/loader using the five retained PDFs through a named downloader
file-return seam. It loaded 541 + 1,041 + 513 + 1,082 + 532 = 3,709 findings,
with 47 attributed chapters per edition and no partial/refused/deferred source.
Seven synthetic protected source/extraction/audit controls and all seeded
county/country columns retained full-column fingerprints. These are disposable
fixture controls, not a production restore or complete preservation baseline.
The new local fifth source ID was 1, not inherited production ID 2534.

Cached repeats created no rows. The existing loader reported two updates from
Decimal-versus-float amount comparisons; every selected audit column had the
same fingerprint before/after. No amount or counter normalization was introduced.
Source bookkeeping can change on a selected repeat; this is not a read-only
command. Dry-run still creates ingestion-job metadata.

The existing county coverage gate still reports **“newest audits run has no
valid county listing”** after bounded success. Full validation was not certified.
Five successful editions alone cannot establish current whole-source inventory
or all 376 accepted coverage cells. The release owner must resolve how a fresh,
qualified current-listing observation and the bounded run will satisfy that
existing gate; do not mark this manifest as live discovery or suppress warnings.

The [existing readiness runbook](2026-10-01-round11-oag-catchup/README.md) and
[decision ledger](2026-10-01-round11-oag-catchup/decision-checklist.md) continue
to control live adoption. In particular, #379 correction precedes the actual
post-correction preservation baseline; verified full backup/restore and an
exclusive writer window remain pending. The S02 shared read-only capture is
preparation evidence, not a full backup, post-correction state or freeze proof.
Later acceptance still requires the actual current-source/coverage and
preservation receipts, full validation, signed backend API invalidation before
frontend acknowledgement, and source/API/rendered acceptance. This local
implementation neither performs nor waives any of those operations.
