# Bounded manual backend follow-up

Base: `c504d8a2031e9fe596b06cf051777cc5d2a4c056`.

The manual `verification.yml` accepts `verification_scope=full` (required choice,
default) or `backend`. Its run name includes the chosen scope and immutable SHA.
Backend scope runs only `test-backend`: frontend, ETL, security, both browser jobs,
and the full quality gate are explicitly skipped. A successful backend-only run
is evidence for backend verification; it does not assert all quality gates passed.
The checkout guard logs that limitation.

Full scope retains all seven CI job contracts and dependencies. The only permitted
job differences from `ci.yml` are the exact scope conditions, frozen checkout ref,
and frozen checkout guard. The offline parity test checks those differences
explicitly before removing them; it does not generally discard conditions.
Backend commands, services, timeout, test selection, coverage reporting and
optional upload behavior are unchanged. `ci.yml` is unchanged.

The guard accepts only `full` and `backend`; omitted scope defaults to `full` for
legacy direct callers. Empty, unknown and hostile scopes fail. Both scopes require
the complete approved SHA to equal dispatch SHA and actual Git HEAD, a manual
event, and attempt 1. There is no retry path or automatic trigger. All six checkout
jobs pass the selected scope into the common guard; the quality gate has no
checkout and runs only for full scope.

## Executed local receipts

- New tests executed against the original workflow/guard: red, including missing
  scope selection and accepted invalid scope. Receipt:
  `REMAINING_BACKEND_SCOPE_RED.log` in the shared verification artifact directory.
- Fixed entire offline workflow suite: **31 passed**, including exact seven-job
  parity, full/default and backend selection, invalid scope rejection, frozen SHA
  and repeated-attempt refusal, optional coverage and PostgreSQL image controls.
  Receipt: `REMAINING_BACKEND_SCOPE_GREEN.log`.
- Critical Python lint and `git diff --check` passed.

No hosted dispatch, repository settings change, production access or provider
write was performed. Root owns the frozen final dispatch and subsequent Actions
shutdown; this change only supplies the explicitly labelled manual scope.
