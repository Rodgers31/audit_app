> HISTORICAL SUBTASK RECORD — superseded for current acceptance. Its commands, counts and remaining-work statements describe an earlier candidate. Do not rerun the fixed-path generators. See [EVIDENCE_STATUS.md](EVIDENCE_STATUS.md) and checkout HANDOFF.md for final integrated evidence. Original receipt/log bytes are retained.

# TikTok implementation and cross-platform PostgreSQL subtask

Checkout `/Users/roger/.codex/worktrees/b15-platforms/audit_app`, branch `codex/b15-platforms`, accepted starting HEAD `06896185005d822c4b29888138b984510dd1fdbd`. Changes are uncommitted for the parent lane. This subtask did not create a PR, migration, process, container, database role or volume. The parent owns final branch/PR/HANDOFF and independent Spec/Standards review.

Owned implementation files:

- `backend/social/adapters/tiktok.py`: actual Accounts API v1.3 adapter, approved-product gate, current creator settings, explicit consent/disclosures/privacy, inspected origin/media/frame-rate validation, durable settings/submission/status checkpoints, direct versus draft distinction, honest public proof and reconciliation.
- `backend/social/adapters/tiktok_http.py`: explicit bounded transport, exact endpoint allowlist, no automatic wire retries/redirects, sanitized failure classifications.
- `backend/social/adapters/tiktok_oauth.py`: configured provider-console authorization URL, exact `tt_user` exchange and rotation, validated returned subject/scopes/expiries and token repr redaction. The durable connection agent integrates its encrypted state and credential CAS.
- `backend/tests/social/test_tiktok_adapter.py`: 77 injected contract tests.
- `backend/tests/social/test_platforms_postgres.py`: 28 unskipped assigned-loopback PostgreSQL tests. This additional parent assignment covers real worker/credential/media integration across Threads/TikTok/X, migration candidate chain, direct/draft quota counters, target-only retries, ambiguous delivery recovery and X budget reservations/admission.

The TikTok public status contract is deliberately narrower than “processing succeeded”: only a completed task returning valid public `post_ids` is Published. Inbox delivery is blocked/manual_action. No username permalink or absence proof is fabricated. A lost acknowledgement without durable task ID retains unknown outcome and the account's reconciliation hold, with no automatic resend. No standard Direct Post fallback exists.

Shared seam requests delivered to parent and consumed by these tests: `TikTokPostOptions` in immutable document/resolved payload, optional inspected frame rate in `InspectedAsset`, server-only product/origin credential fields, native registration/material loader, `MANUAL_ACTION_REQUIRED` block code, combined direct/draft quotas, bounded 1860-second provider fetch signer, and existing paid X reservation interfaces. Parent owns all edits to those shared modules. Conservative TikTok application media caps are 8 MB photos and 100 MB videos, below provider ceilings; no 1 GB in-memory read was introduced.

Commands actually executed from checkout:

```sh
/Users/roger/Documents/projects/audit_app/venv/bin/python docs/social-publishing/b15-platforms/tiktok_capture_evidence.py
B15_PLATFORMS_TEST_DATABASE_URL='<explicit assigned loopback55398 fixture DSN>' /Users/roger/Documents/projects/audit_app/venv/bin/python docs/social-publishing/b15-platforms/platforms_capture_postgres_evidence.py
git diff --check
```

Final source-bound outputs:

- `tiktok-receipt.json`: PASSED, source unchanged during run, normal **77 passed**, optimized **77 passed**.
- `platforms-pg-receipt.json`: PASSED, source unchanged during run, normal **28 passed**, optimized **28 passed**, neither PostgreSQL run skipped. The receipt binds all social Python source, migration source and imported fixture modules, with generator hashes and raw output hashes read back.
- `git diff --check`: exit 0, no whitespace findings.
- Owned PostgreSQL schema census after tests: `owned_fixture_schemas_remaining=0`. Each fixture also verifies its exact schema disappeared. Parent-owned `b15-platforms-db` and named volume remain for parent final cleanup; this agent never stops peer infrastructure. The dedicated Chrome documentation tab was closed.

Retained failures are honest, scoped history: `tiktok-observed-red.txt` is a preimplementation missing-module import failure, not a behavioral regression; `tiktok-delayed-red.txt` is the observed candidate regression that rejected delayed authorized creator choices despite fresh matching settings. The correction requires a fresh dispatch preflight, unchanged settings hash and nonfuture consent timestamp, while stale dispatch checkpoints still fail. `platforms-pg-first-red.txt` captured the native 1800-second URL-lifetime mismatch and an incorrect fixture assumption that authenticated Threads lookup proved public availability; shared media wiring was fixed by parent and Threads expectations retain unknown visibility. Intermediate fixture-development failures are not reported as product defects or final evidence.

Important positive integration controls: X actually publishes and polls through the real Worker with encrypted stored material and two distinct cost reservations of 15,000 microusd; the exact 15,000 remaining-cap scenario denies an unaffordable status read after a known send without resending. Two competing account-locked reserves against a 20,000 cap admit exactly one 15,000 reservation. TikTok's rate rejection retries only its failed destination; its already published sibling is not sent again. TikTok direct and draft histories share six/minute and 15/day accounting, including another publication's target.

Remaining parent code/delivery work: final account/settings/preview UI/API integration and independent executable Spec/Standards review; retain and regenerate receipts after any source change before reporting an integrated exact-source pass. TikTok webhooks are not implemented; documented authenticated status polling is the recovery mechanism in this candidate. No native edit/delete/scheduling capability is advertised. Live product eligibility, approved application scopes and manual/unattended workflow terms, verified URL property, returned OAuth grants, no-cost commercial terms, deployed integration and actual public-post acceptance remain external gates. No live credentials, connections, provider requests, posts, uploads, terms acceptance or paid resources were used.
