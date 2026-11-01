# Manual publishing acceptance and remaining launch decisions

The required workflow is **add media → review each account's exact preview → Publish now → inspect each confirmed delivery result**. The candidate improves discoverability and blocking explanations; it does not activate delivery. Manual publication is a human authorization, separate from automatic generation, approval, scheduling and publishing.

## Candidate behavior

- Media and immediate publication actions are visible in the composer. The saved revision, selected accounts, backend validation, warning acknowledgement and current worker evidence determine readiness. Scheduling remains a distinct action.
- Missing/stale worker evidence blocks immediate publication in the UI. The backend still owns authorization, account/platform eligibility, immutable payloads and current kill switches. Client readiness is not a new server authority or assurance the worker will stay available after a click.
- A successful command means **queued**. Only an actual confirmed provider result can mean **published**. Ambiguous command results retain the original idempotency key; no new-key resend is inferred.
- Direct human publication remains available without an extra mandatory approval click. The separate submit/approve path remains supported. Sensitive revisions require the existing server-identified facts/source attestation.
- System/account publishing, media uploads, workers and financial generation must remain OFF in production. No controls were changed in this task; no direct-send bypass, new provider connection or automatic switch enablement is introduced.

## Executable acceptance

`backend/tests/social/test_manual_media_workflow.py` mounts the actual media and social routers in one inert application. It executes upload initiation/replay, real PNG inspection, preview, immutable media reference and exact destination validation, both direct and separate human review, paused publication refusal, explicit test-local publication, duplicate-command replay, and the queued/unpublished result. Automatic generation, approval, scheduling and publishing remain false throughout. The disabled-media case cannot grant an upload or change controls. No provider call is made by these API fixtures.

Native delivery, PostgreSQL locking/restart/idempotency and restricted-worker role tests are a separate boundary. They run against isolated PostgreSQL, the actual native adapter/repository/worker code, synthetic credentials and intercepted HTTP. They cannot certify production provider delivery or host capacity. The companion media acceptance includes a separate logical cold restore and missing/corrupt original controls.

The coordinator's local evidence directory is `manual-publish-launch-20261101` under the existing admin-redesign evidence root. Its original normal run passed 299 tests with no skips. The optimized run passed the same 299 plus the three mounted-API cases, 302 tests with no skips. These overlapping runs are not added together. Additional owned media PostgreSQL and cold-restore receipts are reconciled in the final validation record.

## Launch gates

| Gate | What is accepted or executable | Remaining evidence/action |
| --- | --- | --- |
| Admin workflow and exact command semantics (#545/#476) | Local rendered UI/browser, mounted API and native worker fixtures; independent reviews accompany this candidate. | Owner review, ordinary merge/deploy review process, then verify the deployed controls still explain the holds. No live send is authorized by this change. |
| Media safety (#490) | Intake/inspection, quota reservation, reference retention, conditional history recovery, archive/retirement controls and adversarial cases are implemented. Previous ffprobe and private-bucket/diagnostic accounting acceptances remain valid within their recorded scope. | Production app-ledger/object backup and independent restore acceptance, actual maintenance/retention ownership, operational report and accepted storage policy. The two 77-byte diagnostics are not application media acceptance. |
| Provider/OAuth ingress (#767/#488) | Current app-level callback filtering, connection holds, native intercepted provider fixtures and previously inspected existing Facebook/Instagram identities. | Earliest upstream callback-query retention evidence; exact applicable provider authorization/permissions and retained-copy/retention decisions. No policy exemption, scope expansion or reconnect is inferred. |
| Worker operation/capacity (#699/#554/#583) | Existing shutdown/restore/custody and bounded execution proofs are preserved. Local worker/role/restart tests exercise real queue logic. | Remaining intended-host representative operation, sustained capacity/reserve and ordinary command-recovery acceptance. A test container is not an active hosting benchmark. |
| Cost/reserve/security/performance (#481/#778/#809/#774) | Existing accepted scoped proofs remain available. This candidate adds no paid resource or hosted run. | Representative operating cost/egress, current reserve/capacity and outstanding measured boundary/performance evidence. No zero-cost operating guarantee or full security clearance is inferred. |
| Source qualification (#802/#801/#848) | Previously accepted source adapters/cohorts and immutable current-source checks remain unchanged. | OAG acquisition/replay, ongoing source admission, defensible borrowing evidence and period-compatible alternate pending-bills coverage remain their own gates. Unknown balances remain unavailable. |
| Scheduled refresh observability | Separate notification candidate reports early admission/source-plan/bootstrap failures and blocked downstream jobs without weakening the accepted-SHA guard. | Observe an ordinary deployed scheduled run and actual incident delivery. No hosted rerun was dispatched in this task. |
| Explicit activation | All release controls remain held. | A separate, bounded owner launch decision after applicable gates are accepted. Automation may remain off when human-approved delivery is eventually enabled; delivery still needs its worker. |

## Fresh read-only production observations, 1 November 2026

The existing Render deployment page still reports Live at `db713b72ccd4c1938e7dac0401f66770379bdb62`. The existing production Nairobi draft page shows Publishing paused, Media storage has not been enabled, Facebook/Instagram connected with publishing disabled, worker heartbeat stale/unavailable, and no publication results. No post, draft, account or environment was edited during this readback.

The existing Render support conversation titled **OAuth Request Logging** was read directly. Its last visible response is an automated waiting notice, following the automated human-escalation acknowledgement; no human answer establishes internal edge/security/diagnostic query-retention or omission boundaries. The Vercel restriction recorded in #767 is not superseded. No support follow-up, upgrade, grant, configuration change or real OAuth request was made. Mail search alone was not used to establish this conclusion.

The rendered observations establish publishing/media/account holds and unavailable worker evidence, not a fresh host process inventory or financial-generation environment readback. The prior financial-OFF/process receipt is `security-final-866-867-20261101/production-after.json`; the task's `readonly-production-observation.json` explicitly records that distinction. No activation was performed.

Any eventual merge/deployment must include the existing reviewed ingestion-pin admission procedure: validate the combined release and production readback first, then admit only its exact source SHA through the separately authorized `INGESTION_WRITE_APPROVED_SHA` update. Until an advancing main revision is admitted, the scheduled writer must refuse it. This candidate adds no automatic pin advancement, guard bypass or authority to update the pin.

These observations do not turn missing provider/production evidence into a passed gate. Completing local implementation cannot honestly certify a live upload/send or representative operating week while those operations remain prohibited.
