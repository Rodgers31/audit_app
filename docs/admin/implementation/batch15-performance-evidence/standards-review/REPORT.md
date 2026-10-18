# Standards and adversarial review

Verdict: **PASS for the reviewed increment; 0 actionable findings.** This is not full-lane or production acceptance.

Reviewed accepted base/HEAD `06896185005d822c4b29888138b984510dd1fdbd`, the unstaged reset-password height hunk, and all four untracked reset-loading fixture files. Exact SHA-256 values, commands, exit codes, and boundaries are recorded in `receipt.json`.

Standards sources: coordination contract, `code-review/SKILL.md`, `adversarial-verify/SKILL.md`, existing route/loading conventions, frontend ESLint configuration, and the reusable legacy browser fixture. No applicable AGENTS.md or repository-wide CONTRIBUTING/coding-standards file was found in the checkout or its ancestors. Historical review reports are not standards.

The height change follows the existing ready-form and Suspense full-viewport convention. The fixture reuses the existing synthetic disposable API instead of adding production branches. Fowler baseline assessed as judgement calls: naming, duplication, feature envy, data clumps, primitive obsession, repeated switches, shotgun surgery, divergent change, speculative generality, message chains, middle man, and refused bequest. None is material in this small diff; documented repository conventions take precedence. Tool-enforced formatting is not reported as a review finding.

Executed verification:

- Original Chrome suite: **2 passed**, desktop1365×900 and mobile390×844; real profile request held, visible spinner verified, footer measured, profile released, ready form verified (`browser.log`, exit0).
- Independent hostile copies: **3 expected failures**, exit1 (`hostile-browser.log`). Removing footer times out rather than passing; aborting the required profile request times out rather than passing; forcing60vh yields a failing footer measurement (540 < 900). Probe source retained. No absent-prerequisite false-green reproduced.
- API adapter exercised through TestClient with uvicorn.run replaced locally: normal and `python -O` passed. Confirmed loopback binding, disposable SQLite, startup mutators off, synthetic identities, local CORS, denied external Origin, unknown route404, blocked requests/httpx external egress, and cleanup on shutdown (`api-normal.log`, `api-optimized.log`). Checks use explicit exceptions, not removable asserts.
- `git diff --check`: exit0.

Numeric hostile inputs are inapplicable: changed production code adds no parser, validator or numeric verdict function. No product/source edits or service lifecycle changes were made. Production LCP, real recovery credentials, dependency qualification, and genuine admin audit pagination remain outside this review.
