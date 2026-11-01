# Admin media acceptance — 1 November 2026

Source authority: read [SOURCE_EVIDENCE_INDEX.md](SOURCE_EVIDENCE_INDEX.md) and its scoped reconciliation receipt first. Source JSON files from earlier review stages are preserved historical captures, not interchangeable current-checkout manifests.
This is inert local candidate evidence at base `db713b72ccd4c1938e7dac0401f66770379bdb62`, not production acceptance or permission to enable uploads, publishing, workers or financial generation. No production environment, credentials, database or object store was read or changed in this lane. Tests explicitly inject fixture credentials, fake object storage or intercepted SDK transports. Container networking is disabled. Runtime fixture switches may be enabled only inside disposable tests; no deployed controls are changed.

The requested add-media workflow is implemented already. The current evidence does not support calling #490 closed. In particular, the older October 8 handoffs predate subsequent accepted scope, host and diagnostic-accounting work; they must not reopen those accepted prerequisites.

## Local execution receipts

- [Vetted development package cohort](local-media-cohort.txt): **767 passed, 17 skipped**, 3 existing warnings, 27.57 seconds. This is a distinct development-package compatibility run, not an extra independent count to add to the production-package cohort.
- [Exact production packages plus isolated test overlay](production-packages-media-cohort.txt): **767 passed, 17 skipped**, 3 existing warnings, 44.32 seconds; exact skipped cases are retained. The runtime executes Python 3.12.16, SQLAlchemy 2.0.55, Pillow 13.0.0 and pytest 9.1.1. This local image has no ffprobe/ffmpeg; actual video decoding is not established by this run.
- [Final strengthened cold reconstruction and mounted API replay](independent-mounted-api-and-cold-restore.txt): **6 passed**, zero skips, 2.29 seconds (three cold cases and three coordinator workflow cases). The [initial three-case receipt](cold-restore.txt) predates a fresh independent inspector/reinspection assertion and is superseded for that strengthened check. A logical SQL export rebuilds an independent SQLite database after disposing the primary in-memory engine. Object bytes reconstruct a fresh fixture store from private temporary files and a fresh inspector rechecks the reconstructed original; original input bytes/SHA256 precede service output. Historical references, quota, pending uncertainty and OFF controls survive. Missing/corrupted restored originals refuse preview. This is synthetic restore compatibility, not independent production backup custody.
- [Runtime readback](production-package-runtime.json) and [immutable image identity](production-package-image.txt) describe the actual local execution; the image tag alone is not the receipt.
- [Source identity](source-before-production-cohort.json) and [stability check](source-stability.json) bind the selected media tests and their social dependencies. The source manifest is a candidate snapshot, not deployed identity.
- [Preserved setup refusal](setup-runtime-path-failure.txt): the archived Linux venv cannot execute directly on the macOS host. No pytest case ran in that attempt; it is not a rejection-control pass. The Linux container runs below corrected that prerequisite.

Run from the repository root, with the independently retained `python-author` directory supplied as an explicit path. No installation or live service is needed:

```sh
docker run --rm --network none --cpus 1 --memory 1g --pids-limit 128 \
  --read-only --tmpfs /tmp:rw,nosuid,size=256m \
  --mount type=bind,src="$PWD/backend",dst=/app,readonly \
  --mount type=bind,src="/Users/roger/.codex/visualizations/2026/10/29/01a1886d-f9ce-70c1-8bdf-14a2bb51c304/admin-redesign/security-final-866-867-20261101/python-author",dst=/evidence,readonly \
  --workdir /app --env PYTHON_DOTENV_DISABLED=1 --env PYTHONDONTWRITEBYTECODE=1 \
  --entrypoint /evidence/docker-prod-test-env/bin/python \
  pr863-python-patch-parity:local -m pytest \
  tests/social/test_media_service.py tests/social/test_media_api.py \
  tests/social/test_media_management.py tests/social/test_media_retained_recovery.py \
  tests/social/test_media_owned_writes.py tests/social/test_media_owned_review.py \
  tests/social/test_media_payload_retirement.py tests/social/test_media_legacy_recovery.py \
  tests/social/test_media_cleanup.py tests/social/test_media_storage_adversary.py \
  tests/social/test_media_inspection_adversary.py tests/social/test_media_inspector_availability.py \
  tests/social/test_media_acceptance.py tests/social/test_media_operator.py \
  tests/social/test_media_maintenance.py tests/social/test_media_object_identity.py \
  tests/social/test_media_privacy_adapter.py tests/social/test_media_reconciliation_boundary.py \
  tests/social/test_media_request_limits.py tests/social/test_revision_asset_admission.py \
  tests/social/test_media_config.py -q -ra -p no:cacheprovider
```

The vetted development run substitutes image `admin-redesign-python:local`, mounts its separately retained backend venv at `/media-env`, and uses `/media-env/bin/python`; the selected tests and other container controls are the same. For the separate cold restore receipt, use the identical production-package container command and replace the test selection with `tests/social/test_media_cold_restore_acceptance.py`; it is a normal collected test with no prerequisite skips. The broad 767-test runs precede this new three-case module, so their counts exclude it.

The 17 broad-run skips are eight unassigned PostgreSQL cases (three cleanup, five maintenance) and nine missing-FFmpeg/ffprobe cases. Tests selecting PostgreSQL skip unless their expressly assigned local fixture exists. The coordinator completed the serial PostgreSQL selections and the separately qualified host video compatibility run. [COORDINATOR_ACCEPTANCE.md](COORDINATOR_ACCEPTANCE.md) preserves their exact counts, overlapping selections and package limits. The [independent skip-inventory reconciliation](independent-skip-inventory-reconciliation.json) confirms all eight formerly skipped PostgreSQL case IDs passed in each mode and all nine formerly skipped native-video IDs passed among 21 host cases. The original broad-run skips remain unchanged in their receipts; host Python 3.14 video compatibility is not production-package parity. This lane started no database or scheduler.

## Launch requirement disposition

“Previously accepted” below refers only to the named issue snapshot/comment, not a fresh November 1 production read. “Locally proven” refers only to the retained execution above. External acceptance and owner approval remain distinct.

| Requirement | Disposition and receipt | Minimal remaining action |
| --- | --- | --- |
| Private bucket, disabled public access, scoped credential metadata, exact-origin CORS | Previously accepted read-only prerequisites: [October 20 configuration and replacement/custody record](https://github.com/Rodgers31/audit_app/issues/490#issuecomment-6299129592). Actual browser/provider writes are not implied. | At the intended release, bind current policy/credential/build/origin evidence to the accepted scope; do not reuse a consumed write allowance. |
| Exact signed length/type/create-only behavior and private browser readback | Locally proven by `test_media_config.py`, `test_media_storage_adversary.py` and the service/API cohort. Earlier browser/provider receipts are independent limited diagnostics. | Retain an app-asset browser/provider acceptance receipt for the chosen scope and explicitly authorized bounded operation. No such operation is executed here. |
| PNG/JPEG byte inspection, hostile bytes, metadata/request limits | Locally proven by `test_media_inspection_adversary.py`, `test_media_request_limits.py`, actual API completion and the production-package run. Fake metadata cannot make invalid bytes ready. | Preserve intended-host resource/ingress acceptance; local container limits are not a hosting capacity benchmark. |
| ffprobe provisioning, valid/corrupt MP4 on actual backend | Previously accepted after [deployed #758, October 19](https://github.com/Rodgers31/audit_app/issues/490#issuecomment-6278520757). Local image lacks the binaries, so its nine native-video skips are disclosed. | Recheck intended release binary/build only if source/runtime changes invalidate the accepted receipt; do not call a local missing-tool skip a production defect. |
| Initiate → inspect → ready library → private preview; retry and actor isolation | Locally proven by `test_media_service.py` and `test_media_api.py`: actual Pillow byte inspection, durable idempotency, scoped completion and URL-free summaries. | Complete ordinary browser/app-host acceptance with uploads off until a separate enablement decision. |
| Historical references and safe unused-asset soft archive | Locally proven by `test_revision_asset_admission.py` and `test_media_management.py`: nonready/deleted originals refused, historical refs block archive, unused settled asset archive retains bytes/quota/audit and works with upload runtime off. PostgreSQL race tests belong to coordinator run. | Accept the human UI interaction and coordinator real-PG race result. Archive is metadata hiding; no physical deletion is inferred. |
| Quotas, both-copy reservations, pending capacity, operator backlog visibility | Locally proven by service/maintenance/operator tests including uncertain outcomes, ledger drift and failed cleanup. Empty ledgers are not physical storage inventories. | Bind actual app-ledger inventory and operational report to the intended host before enabling. No production ledger was populated here. |
| Known conditional histories versus unknown writer histories | Owner-selected boundary previously accepted/deployed in [#753 disposition](https://github.com/Rodgers31/audit_app/issues/490#issuecomment-6256650451); fresh local retained/legacy/owned/reconciliation tests verify recorded histories and hold unknown bytes/quota. | Preserve the chosen support boundary. Unknown/off-system histories remain quarantined; do not invent generic drainage from age, HEAD, leases or deletion. |
| Cleanup/retirement/retention safety | Locally proven by cleanup, payload retirement, privacy adapter, maintenance and object-identity controls, with explicit synthetic authorities. Actual arbitrary-writer quiescence is not certified. | Approve actual retention/deletion policy, bounded maintenance ownership and any concrete retirement authority separately. Keep ready originals unless that separate scope is accepted. |
| Diagnostic object accounting | Previously accepted: [provider samples reconcile 154B payload + 150B metadata = 304B](https://github.com/Rodgers31/audit_app/issues/490#issuecomment-6309169251). The two 77B diagnostics remain separate from the empty application ledger. | Do not reopen the resolved 80B custom-metadata discrepancy or insert diagnostic probes into the app ledger as assets. |
| Backup/restore and independent custody | Diagnostic downloads/local reconstruction previously accepted in [October 22 record](https://github.com/Rodgers31/audit_app/issues/490#issuecomment-6351910798). The new local cold-reconstruction test separately proves synthetic media/ledger/reference compatibility with missing/corrupt-object refusal. Neither receipt proves a production application asset/ledger restore, remote R2 restore, loss-of-source recovery or deletion authority. | Obtain a separately authorized, scoped app-ledger/object backup and independent restore acceptance, including retained references/deletion ledger. A local synthetic copy cannot close production custody. |
| Hosting availability, sustained inspection/worker capacity, egress and representative costs | External operating acceptance under #481/#699; local CPU test results are not sustained production capacity or daily/seven-day operating costs. | Accept the remaining intended-host operating/cost profile without creating a paid resource implicitly. |
| Provider/OAuth/privacy and actual delivery | External gate: #767 ingress-provider response unresolved; #488 provider/permission and retained-copy policy remain independently scoped. This media lane performs no send, OAuth action, credential read or provider contact. | Resolve provider ingress logging evidence and required owner/provider decisions. Existing local native-adapter fixtures do not certify a provider send. |
| Explicit enablement | Owner acceptance outstanding. No local evidence grants production authorization. | Make a separate release decision only after the applicable external gates are accepted. Publishing, uploads, all workers and financial draft generation stay OFF. |

No product fix was needed from the executed cohort. The open work is the bounded acceptance named above, not rebuilding the already implemented intake, reference, recovery or maintenance ports.
