# Issue723 handoff — held draft implementation

Issue [723](https://github.com/Rodgers31/audit_app/issues/723) remains **open and incomplete**. Bounded Facebook Reels and Instagram Reels transport/recovery code is implemented and independently reviewed. A reviewed public-confirmation contract is still missing engineering. Production capabilities exclude Reels, native approval/mutation admission rejects them, and no provider/flag/grant activation occurred. This is not a claim that credentials or a live pilot alone complete the issue.

## Source and implementation

Baseline: `5189675364648113c92b46b54d8f6a30b1bf00e2`; schema source remains `a705b15a0001`, with no migration changes or applications. Implementation commit: `a44a844320c775a908357d677a39bd19ae13411e` (full SHA/source hashes in the external provenance below); exact reviewed implementation tree: `54341ecdc2b954279c8d1bc294a71edfede371df`. The follow-up documentation commit preserves those implementation bytes. Exact PR tip and review snapshot are recorded in `FINAL.json` below, avoiding a self-referential Git SHA in this committed document.

Branch: `codex/b16-723-meta-video-delivery`. Managed worktree: `/Users/roger/.codex/worktrees/b16-723-meta-video/audit_app`. The dirty primary checkout was not modified or used as implementation source.

- Facebook: start an isolated numeric session, accept only canonical documented upload URLs, upload exact inspected bytes, read status, resume the same session from the authoritative offset, and finish with its own public dispatch permit. Persisted operation UUIDs count lost receipts exactly once. Unknown session creation cannot trigger another session; unknown publication cannot trigger another finish.
- Instagram: verified retained-object URL -> `media_type=REELS` container -> bounded processing/quota reads -> publication -> exact owner/product/caption/permalink identity read. Generic Facebook Login does not establish Business Login binary-resume entitlement; no unsupported IG binary product is advertised.
- Both distinguish bytes uploaded, readiness, publication acceptance and public visibility. Unverified accepted outcomes remain Processing then held/unknown. Existing text/image paths remain covered. Plain Facebook legacy video is unsupported.
- An optional typed nonpublic continuation proof binds account, original operation UUID/request fingerprint, approved payload and new checkpoint. Repository/worker revalidate the latest nonpublic intent before clearing only its target's hold. Ambiguous public operations cannot use this proof.
- Authoritative Retry-After deadlines and HTTP status survive status-read rejection. See [the dated official contract and decisions](ISSUE-723-CONTRACT.md).

Shared integration files: `backend/social/contracts.py` adds one optional typed field; `backend/social/worker/runner.py` serializes it; `backend/social/worker/repository.py` validates it transactionally using existing columns/grants. `worker/continuation.py` contains pure binding checks. No API/router, frontend, schema, role or worker-startup changes. These are the likely merge-conflict points with sibling branches; do not overwrite their independent changes.

## Executed verification and review

External evidence directory: `/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/FULL_PLAN_COMPLETION_B16/723/`.

- Final source tree:345 focused tests passed on read-only borrowed Python3.13.9 and cached Linux/Python3.12.15, including11 actual owned PostgreSQL17 cases. Logs: `final-python313.txt`, `final-python312.txt`; `IMPLEMENTATION_PROVENANCE.json` records source hashes. These are overlapping selections on two runtimes, not690 distinct tests or hosted CI. No Node/frontend source changed.
- Actual Studio MP4 rendering/decoding/review/attachment and exact checksum approval were executed; retained-media access and full repository/worker checkpoints/restarts exercised. Dormant transport execution uses visibly named test-only offline capability subclasses. Real production registration separately refuses a forged expanded persisted snapshot before any transport.
- Baseline four-case missing-format/transport regression was observed red, then green. Direct numeric guard regressions were observed red for boolean/zero/negative sizes, then green. Full-worker lost-upload-receipt continuation was observed blocked before the proof integration, then resumed safely.
- Standards independently reproduced six uploads after repeated receipt loss; author reproduced it and ran a failing regression before fixing UUID accounting. Final independent PostgreSQL worker check observed exactly five uploads/five durable intents, holding the sixth cycle. Same UUID reconciliation twice stays count1.
- Spec independently reproduced discarded Retry-After and improper Reels admission without public proof. Author ran two-platform rate and production-capability regressions red, then green. Status429 now retains3600s; actual adapters refuse Reels with zero transport calls.
- Standards: zero unresolved implementation findings on tree54341ec. Spec: identified implementation defects corrected; **public-proof integration remains an unresolved scope requirement**. Reports: `review-standards/REPORT.md`, `review-spec/REPORT.md`, `review-spec/FOLLOWUP-54341.md`. Independent177-case selections/hostile probes overlap author coverage and are reported separately.
- Chrome: official Meta product pages were read in the existing authenticated Chrome using a task-owned tab. `official-*.txt` plus `official-instagram-media.png` retain evidence. No frontend UI changed; no live publication or UI-to-provider flow is claimed. A separate IG-media reference lookup returned only page shell, not a usable public-visibility contract.
- Preserved setup failures include a wrong fixture path, missing Linux `ps`, and an invalid test-file selection; corrected runs above executed the actual cases. They are not counted as rejection passes. FFmpeg/procps were installed only in a disposable local fixture derived from an already cached image; no dependency/lock changes or paid resource was added.

## Remaining checklist and acceptance

1. Establish and implement an independently reviewed official public-outcome proof for these exact products, including private/restricted/unavailable cases; keep Reels unavailable until then. No invented visibility field or owner-authenticated permalink may substitute for that proof.
2. Complete remaining media/product qualification as needed by that contract, then rerun real admission and dormant-flow tests together. Existing source/byte custody stays mandatory. Do not broaden into legacy Facebook video or activate another provider product to bypass the gap.
3. Only after engineering is complete, separately accept provider access, exact account capabilities, media retention/storage, effective roles, host ownership/capacity and a permitted bounded live pilot. No live access test, actual upload/post, production mutation, schema application or worker start occurred here.
4. Draft PR is held; no merge/deploy/auto-merge, bot review request, Actions run, manual Vercel preview or issue closure is authorized by this handoff. Existing Actions disabled state was read back asfalse. Existing production/preview tracking was not changed.

Parent #476/#545 and issue723 remain open. No sibling #722/#724/#727 work is absorbed. Cleanup receipts for exact owned fixture containers/volumes and reusable loopback port are retained in `cleanup.json`; other sessions' resources are untouched. The managed worktree remains attached for review and continuation.
