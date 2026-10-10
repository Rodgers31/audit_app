Independent Spec follow-up — 2026-10-09

Source: `git diff 672c5c011ce57dc41551f5fbc642bc4e69134c43...d16c5a43d7e94fde2799afe9ecaf93ac2400ebd7`; candidate tree `a304a9f632a3e4d700038cac3cb6b53c1a13185e`. Spec remains the Batch 9 assignment and [#494](https://github.com/Rodgers31/audit_app/issues/494). This is a new review record; `spec-review.md` remains historical.

**One confirmed finding [P2]: malformed npm identities still receive a successful graph verdict.** The assignment requires “malformed or incomplete reports must not become successful verdicts.” The new name regex rejects whitespace/uppercase identities, but accepts `.invalid`, `@scope/.invalid`, and reserved `node_modules`. With the four required callers plus each invalid row, the actual graph-gate child exits 0 with `tests 1 / pass 1 / fail 0 / skipped 0`; npm 11.6's own validator returns `validForOldPackages:false`. Complete the package-identity invariant and extend its regression. This tests an inert report boundary, not an installed-tree exploit.

The effective ESLint repair is in scope: the public `calculateConfigForFile` API inspects inherited/override/descendant/alternate configuration across Next's default lint directories/extensions. Both CLI and CSS verifier await the async guard. Read retained `red-effective-config`, `red-report-name`, and `green-effective-config` outputs: the previous bypasses failed their new regressions, then all 15 controls passed with no skips. These are inspected author receipts, not independently repeated tests. Next's installed `runLintCheck.js`/`next-lint.js` confirm the retained default directory/extension contract. No scope creep identified.

**#494 remains partial/open.** Lock, discovery and Tailwind/PostCSS/ESLint configuration are unchanged (`git diff --exit-code <base> <candidate> -- frontend/package-lock.json frontend/jest.config.js frontend/tailwind.config.js frontend/postcss.config.js frontend/.eslintrc.json`: exit 0, empty). Native/browser chains and search behavior are unchanged by this diff. Final handoff/committed delivery and repaired platform acceptance remain pending; no closure, production or hosted execution is certified.

Executed reproduction on owned macOS arm64 Node `v22.19.0`/npm `11.6.0`:

```sh
node docs/admin/implementation/batch9-dependencies-evidence/run.cjs spec-report-name-red /Users/roger/.codex/worktrees/a486/audit_app node docs/admin/implementation/batch9-dependencies-evidence/spec-report-name-control.cjs
```

Outer exit 1 means the invalid reports were incorrectly accepted. Exact child commands/output are in `spec-report-name-red.stdout`; outer command/source/provenance is in `spec-report-name-red.json`. Provenance was read back and the control hash matched its on-disk file. SHA256: recorder `7de734d0b00d8bb3bfdbc081c21d763dc8ec385603bf163a637ad9f03e35f9d8`; control `7173aa3c421794981f083e921265882eb8466a6f65f780a0949815a407534308`; tested gate `646dbefac0e4de430be2ebae2cde22e59c5f3b5f798bb552da0e4d3a2c294b76`; npm validator `903c4513191f3413c0b67e6eded261e303fe83d9b9a968d0d05b0bc639b4d3f8`.

No implementation edits, services, installations, commits, pushes or bot requests. Owned temporary report fixtures were removed.
