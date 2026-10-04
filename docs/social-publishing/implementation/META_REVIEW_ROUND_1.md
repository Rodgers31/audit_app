# PR #489: navigation and status review receipts

Reviewed against frontend baseline `01c39a8ff82395aa2afa7df119529ac6f0271658`. Changes are frontend behavior and isolated tests only; no live OAuth, provider request, operational configuration, dependency installation or database operation occurred.

## Finding dispositions

- **Valid, recurring stale UI:** [Copilot inline comment 4175474494](https://github.com/Rodgers31/audit_app/pull/489#discussion_r4175474494), thread `PRRT_kwDOPmNsm86otNXW`. The old Accounts button changed the local view instead of navigating. The obsolete view and duplicate navigation were removed; one Accounts link opens `/admin/social/accounts`. The real composer already guards document link clicks for unsaved drafts. Tests execute the real Next Link with router contexts: cancel preserves content, accepting navigates once, and each click prompts once. Similar unconditional unavailable claims were removed from the empty composer and empty Meta account list. Actual configuration blockers remain visible on the connection page.
- **Valid frontend contradiction, server already fail-closed:** the [review-body-only decoder concern](https://github.com/Rodgers31/audit_app/pull/489#pullrequestreview-5403535634). `available=true`, `blockers=[]`, `access_mode=unverified` passed the decoder, although backend configuration always adds `ACCESS_MODE_UNVERIFIED` for that mode. The decoder now rejects this contradiction. It continues accepting configured `owned_standard` and `advanced`; this does not introduce business-verification or provider-proof requirements. Unavailable responses remain unavailable without imposing additional blocker-code coupling.
- **Related actionability defect:** a rejected status refresh leaves the previous available DTO in TanStack Query. The common connection-availability guard now also requires no current status error. Connect, reconnect and the start handler use that guard. Recovery, explicit selection, disconnect and actor/mount epoch checks retain their existing semantics.

## Executed red/green evidence

The new navigation and status fixtures initially reported **5 failed, 11 passed** against the original frontend. Failures were actual router navigation (including the unsaved-decision path), stale composer copy, the unverified/available matrix cell and the real account-management UI consuming that contradictory API response. Both configured-access empty-state tests subsequently failed against the old Meta list copy.

After fixing the decoder, the retained-data status-refresh fixture still failed because Connect remained enabled. Removing only the status-error guard then independently reproduced **2 failures** for Connect and Reconnect. Restoring it made both pass. The matrix exercises all 12 combinations of the three access modes, availability and empty/nonempty blockers. Positive UI cases prove that both authorized access modes remain actionable.

Backend `ConnectionService.status()` was also executed using a fake database executor and fixture-only configuration, without HTTP or SQL. It returned:

```json
{"available":false,"access_mode":"unverified","blockers":["ACCESS_MODE_UNVERIFIED"]}
{"available":true,"access_mode":"owned_standard","blockers":[]}
{"available":true,"access_mode":"advanced","blockers":[]}
```

Final commands, run from `frontend` using the existing bundled Node runtime and dependency symlink:

```sh
node node_modules/jest/bin/jest.js --runInBand --no-cache __tests__/admin/social __tests__/social-connections
node node_modules/typescript/bin/tsc --noEmit --incremental false
node node_modules/eslint/bin/eslint.js components/admin/social/SocialWorkspace.tsx components/admin/social/SocialComposer.tsx components/admin/social/connections/MetaAccounts.tsx lib/api/socialConnections.ts __tests__/social-connections/review-navigation.test.tsx __tests__/social-connections/status-review.test.tsx --no-cache
```

**298 tests across 18 suites passed**, including 20 new review cases. TypeScript and scoped ESLint passed. No mutation test contacted a real provider or published a post.

## Similar call sites and residual boundaries

All workspace sections share the single Accounts route link. The composer remains responsible for dirty-document link navigation; local section/queue changes keep the workspace's existing confirmation. Both empty-account surfaces now describe account absence, while configuration availability is reported only from status.

`connectionApi.status → decodeConnectionStatus → useMetaConnectionStatus` is the status boundary used by the account page. Its common guard covers the Connect button, every account's Reconnect button and the start handler. The existing session-bound GET recovery path and authenticated completion/selection/disconnect commands remain intact. Runtime configuration is still disabled by default; publishing adapters remain absent. The deployed keys/roles/logging and actual Meta app/account/callback validation in #488 remain operational gates. No PR reply, resolution, push or merge was performed in this review work.
