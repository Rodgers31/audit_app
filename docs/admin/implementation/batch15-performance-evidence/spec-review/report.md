# Independent Spec + adversarial review

Reviewed 2026-10-16, worktree `/Users/roger/.codex/worktrees/b15-performance/audit_app`, HEAD/base `06896185005d822c4b29888138b984510dd1fdbd`, unstaged candidate plus four untracked fixture files. No source edits. Read code-review/adversarial-verify skills and full COORDINATION.md; no AGENTS.md found inside this checkout. Standards axis belongs to the separate reviewer.

## Spec findings (partial scope, not defective implementation)

No actionable defect found in the minimal fix. Replacing auth-loading `min-h-[60vh]` with `min-h-screen` makes its minimum height match the existing ready-form container, removing the demonstrated visible footer intrusion. This is required layout repair, with no unrelated redesign.

The lane specification says “Finish required reported performance/dependency work under #481/#494/#611/#545” and “Genuine production audit pagination cannot be certified with manufactured events.” This candidate is a coherent partial increment only. It does not complete dependency remediation, source-bound live performance acceptance, real audit pagination, or parent #545. No manifest or lock changes exist in the reviewed diff. The baseline observation bundle correctly says OBSERVATIONS_ONLY and synthetic=true; the fixture README explicitly disclaims real recovery, production LCP, and audit pagination. No false closure claim found in those reviewed materials. Keep remaining requirements explicit in delivery.

## Executable evidence

From frontend:

1. `node node_modules/playwright/cli.js test --config browser-fixtures/reset-loading/playwright.config.ts --output <this-directory>/playwright-output` — exit 0; 2/2 Chrome tests pass. Raw `test.log`.
2. `node node_modules/playwright/cli.js test --config <this-directory>/playwright.config.ts --output <this-directory>/adversarial-output` — exit 1 as expected; two wrong-layout mutants fail, two 503-profile mutants pass. Raw `adversarial.log`; exact standalone mutated specs/config retained here.

The wrong-layout mutant injects a MutationObserver before navigation and assigns the loading spinner parent min-height=60vh. Actual failures: desktop footer y540 <900; mobile y506.390625 <844. This independently confirms the test detects the original layout, without rebuilding/stopping parent-owned servers. Parent red-loading-test-attempt3.log reproduces these same failures on its original production build; parent green and candidate build receipts inspected.

503-profile mutation passes because the check measures loading/ready layout, not authentication validity. This is an explicit boundary, not a false green for the stated layout requirement. Do not cite the test as functional auth or successful profile proof. The route promise fails closed via Playwright timeout if a profile read never occurs; spinner visibility and final form heading prevent an empty-page pass.

Current local .next BUILD_ID: dV3tplQWcK5YCuvSUhXeM. reset-password chunk page-3bfb1bdcce5705e0.js SHA256 e41e61a28b01c30c72bb802c049e4a9312bbc0a0031135999e88a3a4fcf86e06 (3 min-h-screen occurrences, no 60vh). Original page SHA256 6a1db35e821597cb60a89eb8ec36b3f3f0829e2cb82b27b8035ca7abce13f684. Exact reviewed source hashes are retained in source-hashes.json.

No cloud/provider operations, credentials, installs, build/server restarts, source mutations, or new services. Only owned Chrome test processes created; runner closed them. Existing parent-owned servers remain untouched.

Conclusion: minimal repair and regression accepted for this limited layout scope; broader lane remains partial. No blocker within reviewed candidate.
