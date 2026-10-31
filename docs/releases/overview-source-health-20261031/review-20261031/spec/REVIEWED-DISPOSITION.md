# PR #863 review disposition — 2026-10-31

Reviewed body: [Copilot review 5724037772](https://github.com/Rodgers31/audit_app/pull/863#pullrequestreview-5724037772), on `253ab29978fdb546b001381861eb767fe84b633f`.
The complete initial census has one COMMENTED review, no inline comments,
issue comments, unresolved threads or pending human/bot requests. The review
body's three moderate findings concern the same optimized-assertion hypothesis
at three historical runner paths; they are classified below. A separate
request for live verification is retained as a deployment gate.

## R1 — refuted: optimized pytest assertions are missing

Affected paths are `standards/run_review.py`, `run_final_review.py` and
`run_canonical_affected.py` in the original release packet. They invoke the
default `python -O -m pytest` assertion mode, with no `--assert=plain` override.

The claim was executed, not dismissed from source inspection. Root deliberately
failed a collected test assertion and a helper assertion under the optimized
interpreter: two expected failures, one runtime-check pass, exit 1. Root also
replayed the original independent module with only its expected cooldown
changed from 26 to 27: the original helper assertion failed, with 31 other
checks passing, exit 1. These failures occurred at the intended assertions.

Standards independently exercised all three retained command shapes. Each
false-assert canary exited 1. The unchanged original 31-case module plus its
runtime canary passed 32; the one-literal mutant failed in `denied` as expected.
All five processes recorded `sys.flags.optimize == 1`, `__debug__ == False`
and pytest's AssertionRewritingHook. The same-module helper's rewritten
bytecode is retained. All 33 original sealed artifacts remain unchanged.

Spec independently executed the three actual historical argv builders with
controlled false test/helper assertions and observed child exit 1 for each.
An explicit `--assert=plain` calibration then false-greened, establishing that
the probe detects the difference. No plain-mode option was introduced into
the accepted runners.

Python still removes ordinary unrewritten assertions under `-O`. Pytest's
warning concerns those outside rewritten test modules/plugins. The conclusion
is limited to these collected modules and their same-module helpers; it does
not certify arbitrary imported application helpers. Keeping application code
optimized while preserving test assertions is the intended validation mode.
No application or historical runner change is warranted for this finding.

## R2 — valid: live provider and rollout verification

Offline acceptance does not certify a deployed release. Before rollout, a
fresh read-only production check confirmed backend `12b79d3`, false publishing
and automation controls, media false, default-off financial/native generation
and supervisors, no worker/consumer process, five posts and zero publication,
target, media or attempt rows. The deployed frontend is still
`dpl_7FSLXMFFtcQ89hxg2x86mgzst7V7`.

The fresh local production prebuild uses the existing project's pulled
production configuration. All 838 frontend source pins match the reviewed
candidate. It has 104 logical Node 24 functions and one Edge function, with
98 deduplicated aliases; physical Node bundles are x86_64. The API rewrite
still targets the existing Render backend. It has not been uploaded.

Required after the authorized rollout: inspect the actual authenticated
Overview and its seven read panels, response advice/CORS and provider-key
integration; verify installed source hashes and production configuration;
recheck the direct CoB observation and accurate failed KNBS/Treasury reasons;
and read back all four OFF controls, counts and processes. A successful reload
alone does not prove an observed cold-cache refusal/retry transition. Record
that narrower limit if no natural refusal occurs; do not manufacture an outage
or weaken authentication/TLS to create one.

## Merge boundary and scope

The merge helper's only code delta from the previously exercised coordinator
is the PR allowlist changing to 863. Spec executed 50 controls normally and
50 under actual `-O`: ordinary success, policy rejection, explicit override,
fresh second census, failed override, unexpected errors and 19 invalid-census
states at initial and late boundaries. There were no external GitHub calls.
Draft, changed head, new review material, pending bot/human review, unresolved
or incomplete threads, requested changes, failed checks and closing references
refuse. A first synthetic baseline accidentally inherited the actual draft
state; its setup failure is retained, then the intended ready-state fixture
passed. Actual draft refusal has its own negative control.

This round changes review evidence/documentation only. The eight original
executable source/test pins remain unchanged; the existing application
acceptance results carry only on that verified identity. Historical evidence
is not rewritten. This addendum has its own `SHA256SUMS`.

No paid review, hosted test rerun, new resource, plan change, activation,
migration, generation or business-data write is part of review preparation.
Automatic review/new-push/draft controls are read back off, and existing Vercel
preview deployment disabling remains unchanged. A normal merge must be tried;
any owner override needs the explicit authorization for this PR. The rollout
record is separate and must identify the actual merged/deployed SHA.
