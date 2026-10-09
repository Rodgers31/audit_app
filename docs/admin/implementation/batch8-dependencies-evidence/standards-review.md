# Independent Standards review — Batch 8 dependencies

Fixed source `97fe77462b4e63ffad7dc393b8bf97d3e51571f7`, tree `f22a430a4402d79867da63ad97db8c8d474d3a71`; uncommitted review uses `git diff 97fe77462b4e63ffad7dc393b8bf97d3e51571f7` plus the new Jest boundary test. No post-base commits. Re-reviewed all four final product files and the unchanged 313 exact before/after lock records. Current hashes are in `checks.json`; graph test SHA256: `ae7b43c389bc8a8457ecc69f43ec4ab2e01dfc6821e676606fbe1cdb90a7e830`.

**Documented-standard breaches: 0.** Sources: `CONTEXT.md`, `TESTING_GATES.md`, frontend README Contributing, current ESLint settings, Batch 6/7 acceptance briefs and dependency handoff; no applicable `AGENTS.md` found. Financial terminology is untouched. The CommonJS test follows existing dependency-script conventions. The short CLI helper is not complex enough to trigger the README JSDoc guidance. Tooling-enforced style and quality gates are excluded from standards findings.

The package script extends the existing required boundary command, retaining browser controls and the runtime/source-isolation regression. Explicit application discovery preserves the earlier patterns while keeping Node fixtures outside Jest. The repaired installed-graph gate validates every package row and requires four actual caller identities. Its new self-spawned negative controls exercise that same gate with incomplete or malformed measurements; the anchored test selector prevents recursive execution. Other CLI controls cover discovery, successful execution, real assertion failure and malformed configuration.

**Fowler heuristic findings: 0.** No actionable smell was established. The `jest(args)` helper supplies a shared CLI/root/timeout policy. Short purpose-specific fixture setup and cleanup does not justify a new abstraction.

Read-only Node 22.19.0 checks pass: new test syntax; supplied lock delta matches current source; 173 baseline production records are byte-identical. Changes comprise one root record, 77 additions, 138 removals and 97 modified development records. New/changed install-script packages remain development-only.

**Limits:** this reviewer did not execute runtime Jest, boundary suites, frontend coverage/lint/build, native/browser, Linux or hosted gates. Final handoff/evidence documentation review is pending. This report establishes standards review, not deployment/security acceptance. Initial reports/checks are preserved separately.
