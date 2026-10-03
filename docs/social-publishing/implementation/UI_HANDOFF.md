# Batch 1 social admin UI handoff

Implemented on 2026-10-03 in the isolated worktree `/Users/roger/.codex/worktrees/social-composer/audit_app`, branch `codex/social-admin-composer`. The approved Queue and preview HTML is the design reference. Existing `PageShell`, admin identity/guard, authenticated Axios, colors and typography are reused. No billable design generation was invoked.

## Delivered

- `/admin/social`: compact, paginated drafts/pending review/scheduled/history queue and actual connected accounts. Selected detail opens beside the queue; `/new` and `/[postId]` provide full composers. Scheduled/history filtering is explicitly limited to the current compact page because batch 1 exposes only the editorial server filter. Counts never pretend to represent all deliveries.
- Manual master text, HTTPS website/source references, hashtags, account selection, provisional capability/format hints and account preview tabs. Sparse text/link/hashtag/media replacements preserve intentional empty values. Reset removes the override key. Missing saved accounts remain selected until explicitly removed.
- Existing media references retain order, alt text and caption identity. Server-inspected fixture metadata renders in previews. Upload/library controls truthfully stay disabled; no upload endpoint, signed preview URL, image bytes or simulated upload result was added.
- Save draft, save and validate, submit, approve, reject with reason, publish, schedule, cancel and duplicate use the frozen routes. Publishing accepts the exact validated selection; an approved publication whose targets are still ready can subsequently publish/schedule. Queued/in-flight/cancelled publications cannot be submitted again through these controls.
- Schedule resolves the future civil time in the selected IANA zone, defaults to Africa/Nairobi, rejects nonexistent times and requires an offset choice for DST folds. UTC preview is explicit. Backend validation remains authoritative.
- Per-account results and verified HTTPS links appear independently. Safe retry is offered only for a failed target and requires a reason; unknown/reconciling outcomes show a reconciliation message and no send button. Versioned global controls require a reason and display missing/stale worker health truthfully.
- Mutation keys survive network/decoder/unconfirmed failure; after a confirmed decoded success the key is released so a later deliberate retry/duplicate is a new intent. Response correlation rejects stale or wrong-post saves, changed saved content/selection, and empty/partial/duplicate/wrong-post publication receipts before cache writes or success announcements. Pending command completion updates the original actor's cache scope.
- Local edits survive optimistic version conflicts. Loading the current revision requires explicit discard acknowledgement when there are unsaved changes. Browser unload, internal links and queue/filter/page changes warn about unsaved edits. Public dispatch locks editing and leaves duplicate available.
- Queries are actor scoped, use cancellation signals, and do not add React Query transport retries. Accounts, lists and system status are not timer polled. Only active delivery views poll the integrator-approved `GET /posts/{id}/status` **PostSummary** every 15 seconds; hidden, terminal, malformed and inconsistent states stop polling. Same-version status merges only delivery fields with the same revision ID. A newer version triggers one full-detail refresh, never a summary/document merge.
- Mobile editor/preview switch, fully wrapping titles, fixed Save/Publish footer with form clearance and safe-area padding, 44px controls, visible focus, labelled inputs, field error descriptions and live status/error announcements.

## Final verification

Run from this worktree's `frontend/`; the existing primary `node_modules` is reused only through a read-only symlink. All generated caches and render outputs are local to this worktree.

| Check | Command | Final result |
|---|---|---|
| Interaction/API/hook/adversarial tests | `SOCIAL_VISUAL_DIR=.social-preview ./node_modules/.bin/jest __tests__/admin/social --runInBand --cacheDirectory .social-jest-cache --silent` | **9 suites, 87 tests passed; exit 0** |
| Whole-frontend typecheck | `./node_modules/.bin/tsc --noEmit --incremental --tsBuildInfoFile .social-tsbuildinfo` | **Passed; exit 0** |
| Lint owned code/tests | `npm run lint -- --dir app/admin/social --dir components/admin/social --dir __tests__/admin/social --dir tests --file lib/api/social.ts --file lib/hooks/useSocial.ts` | **No ESLint warnings/errors; exit 0** |
| Browser fixture verification | `node tests/socialVisualCheck.mjs` | **Passed** at 1440, 768, 390 and 320px: no horizontal overflow, title wraps, no undersized visible buttons, no unlabelled inputs; mobile Preview and 3px keyboard focus pass; mobile footer does not cover heading |

The browser harness renders actual components through the optional Jest fixture export and serves those static HTML/CSS files on an ephemeral loopback port. It blocks every external browser request and closes its own server/browser. It does **not** verify live authenticated routing, production hydration, real worker operation or provider publishing. Interaction behavior is covered by executable React tests with explicit API fixtures. The approved HTML and implemented desktop/mobile states were visually inspected. Fonts use the available fallback in this network-blocked fixture check.

Reproduce the browser artifacts:

```sh
SOCIAL_VISUAL_DIR=.social-preview ./node_modules/.bin/jest __tests__/admin/social/visual.test.tsx --runInBand --cacheDirectory .social-jest-cache
./node_modules/.bin/tailwindcss -i app/globals.css -o .social-preview/global.css
node tests/socialVisualCheck.mjs
```

Review screenshots and browser measurements are in [previews](previews/). Every screenshot uses labelled test fixtures, not actual connected accounts or publication success.

Two adversarial reviewers executed the parsers/hooks and publishing gates. Their failures were reproduced before fixes and retained as regression tests: contradictory/duplicate account validation, ready authorization membership, rejection invalidation, unsafe numeric versions, wrong revision/post status, heartbeat expiry, actor changes during commands, and stale/wrong/partial receipts. The integrator's mutation-intent regression is also included. Initial test harness issues and two visual-export TypeScript mistakes were fixed; the table records the final run. `next lint` emits its existing deprecation notice; the CSS CLI reports stale Browserslist data. Neither is a validation failure; no dependency update was performed.

## Integration boundaries

No remaining UI implementation blocker. The integrator added the shared Social Media admin-navigation link and rebased this branch onto the combined domain/worker core, including the compact status route. Runtime DTOs were checked against the domain agent's `api.py`/`contracts.py` with explicit integrator authorization: nullable reference label/media alt text/unavailable validation platform, capabilities, controls, worker metadata, cancellation and retry-detail DTOs are aligned.

Publishing remains off by default on the server. Actual OAuth accounts, media storage/uploads, live provider adapters, generation/automation, production migration/hosting and deployment remain later work. No production mock data, shared auth/middleware/Axios/package edits, primary checkout modifications, existing-server changes, live social/auth API calls, dependency installs, push, PR or merge were performed. No production Next build or live-route end-to-end check was attempted; the parent integration owns those checks.

After the UI commit is reported, this worktree's tracked files are frozen for the integrator to rebase. The isolated dependency symlink and generated `.social-*` caches are not committed.
