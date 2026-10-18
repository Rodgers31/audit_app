# #722 — bounded Studio source and exact media selection

Implemented on baseline `5189675364648113c92b46b54d8f6a30b1bf00e2` (confirmed locally). Implementation head: `b3c1810cbb62a28c6a609b55bc56718095e63443`; subsequent handoff-only commit does not change implementation. Final delivery head and PR URL are recorded in the author chat and external `delivery.json`.

## Result and integration

Studio offers explicit previous/next source and media pages using the existing20-row APIs. It fetches one chosen source body, keeps its selected label visible across summary pages, and performs no automatic all-page scan. Inspected asset choices require ready state, exact approved SHA-256 and the render MIME type. Attachment requires the active source ID/revision and selected asset on the active page; any pending/failed source, media or job refresh blocks it. Source changes clear editorial text/facts and attachment selection; job/page changes clear attachment state. Query keys bind job/checksum/page, and source/media requests receive cancellation signals. Existing server input-hash/revision/version/inspection and transactional attach guards remain authoritative.

Only Studio, its tests, inert browser fixture and this issue's handoff changed. No shared backend API/contracts/worker edits, schema/role implications or sibling composer/list conflicts. No dependency/lock changes. Publishing/uploads/native processing/supervision/provider activation unchanged; no production mutation, hosted CI, bot-review request, preview, deploy, migration or new resource.

## Executed validation

Evidence root: `/Users/roger/.codex/visualizations/2026/10/13/01a13546-5f5a-7973-925e-a8a2c3aedb7c/FULL_PLAN_COMPLETION_B16/722`.

- Node22.19.0, owned exact-lock npm ci, Jest30.5.2; repository tooling repairs applied only to this worktree's node_modules. Initial read-only borrowed environment proved lock-file parity but had Jest29; those preliminary runs are retained separately and are superseded by owned exact-lock runs.
- `cd frontend && node node_modules/jest/bin/jest.js __tests__/admin/social/studio-selection.test.tsx __tests__/api/socialStudio.test.ts --runInBand`:22 passed (13 selection +9 decoder cases). Forced cached source/media/job network failures, stale revision, mismatched hash/MIME/state, pending/late responses, source changes and attach conflict. Baseline replay with the exact owned runtime:11 failures at the missing next-source control (`logs/722-exact-red.log`); fixed review regression:1failed/10passed before job-refresh guard, then20passed including API; final22passed. The later two tests add conflict/late-asset coverage; no claim they were part of the initial baseline run.
- `node node_modules/typescript/bin/tsc --noEmit`:pass. Full `npm run build`:pass with synthetic localhost API/Supabase public configuration. First build without Supabase public inputs failed; both logs retained. No real credentials used.
- `PYTHONPATH=backend /Users/roger/Documents/projects/audit_app/venv/bin/python -m pytest --confcutdir=backend/tests/social backend/tests/social/test_studio.py backend/tests/social/test_b15_review_studio_input.py -q`:24passed on Python3.13.9 with actual local FFmpeg/ffprobe and isolated SQLite. Actual render, approved-byte integrity, restart and service attach paths executed. Shared interpreter borrowed read-only; source imports use this worktree.
- Cached image `b15-worker-runtime:tests` (`fdf77fbd6b0e`), `--pull=never --network=none --read-only`, owned /tmp, read-only source bind: Python3.12.15,9passed/6deselected for hostile composition/provider/calendar cases. Image has no FFmpeg; no Python3.12 real-render pass or PostgreSQL concurrency qualification claimed. No DB/schema/transaction change required a new PostgreSQL fixture.
- Existing authenticated Chrome extension, own task tab, real component/query/Axios/decoders with local inert HTTP fixture containing21 sources/assets. `/red` baseline had no next-source button or older source. Candidate in dev and production-built `next start`:source page2 → existing approved job → asset page2 → exact inspected asset → existing attach POST with expected_version7 and exact UUID. Enter operated new pagination and attach. Production fixture advanced revision and attachment became disabled. Screenshots `chrome-red.png`, `chrome-green.png`, `chrome-production-green.png`; `http.jsonl` includes genuine request/key. Reviewer `standards-*` keys identify separate inert HTTP failure checks. This is UI/client/HTTP integration; backend execution is the separate receipt above. No live provider/upload/publication call.

## Independent review and disposition

Standards and Spec agents independently executed adversarial suites:11 and10 passing cases respectively after repair (overlap with author tests; counts are not additive). Both bound the unchanged Studio SHA-256 `606503ad84c252808b38add660d76a180b00c0d48e76a2d89172067cf6c997da`. Reports/commands and scratch cases are in `review-standards/` and `review-spec/`.

One valid P2: cached job data stayed actionable after failed refresh. Finding and proposed fix evaluated separately; reproduced in default suite before adding both pending/error guards to the common attachment predicate. Red/green receipts retained; independent rerun passes. No unresolved confirmed review finding. Native select labels, button names, status live regions and keyboard actions preserved; no WCAG conformance or screen-reader audit claimed.

## Remaining checklist

Draft PR only; root must integrate/accept/merge and refresh complete GitHub review state at the exact final head. Issue722 and parents476/545 remain open. Provider/storage/worker/host acceptance and feature activation remain separate. No actual production/source history or provider permission was used as proof. Browser fixture server is stopped at author closeout. Existing Actions workflows remain disabled; no hosted verification or formal GitHub approval claimed.
