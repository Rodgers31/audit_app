# Generated-draft copy readiness

The composer previously told every generated draft that its caption, tags,
destination and sources were prepared. Three existing production drafts still
use legacy renderers with empty master tags, so that unconditional statement
was incorrect.

The generated composer now identifies missing caption, AuditGava destination,
tags/topic, source references and selected/available accounts. It resolves each
account's overrides, including explicitly empty replacements. Repeated platform
accounts are named separately; duplicate friendly names receive a unique account
identifier. Dirty copy, unavailable account reads and a source-review refusal have
explicit states. Complete-looking fields say **Review saved copy**, without
claiming that source authority, editorial policy or publishing eligibility passed.

This is an informational presence check. Authoritative source, validation,
attestation, account and publication gates are unchanged. Deliberate human edits
still receive the existing server policy. No API, database schema, generation,
worker, upload or publishing switch changes are included.

## Validation

- Five new component regressions were observed failing against the original
  message while all eight existing preparation/media cases passed.
- The review-discovered repeated-platform ambiguity was independently reproduced
  in three account-name scenarios and in the permanent author fixture. The
  explicit source-review status was separately seen failing with only that
  product guard removed, then passing after restoration. Earlier test selector
  and timing setup failures are retained separately.
- Full frontend: **215 suites, 2,904 passed, one existing guarded skip**. The skip
  is the optional PostgreSQL HTTP-capture consumer in
  `BudgetTab.debtAbsence.test.tsx`; no new readiness test is skipped.
- Actual-root production build, type checking and **14 browser cases** pass,
  including desktop/phone legacy-copy states and the mandatory navigation gate.
  Lint has zero warnings/errors.
- Independent Spec: **104 executed controls**, including 74 helper boundaries,
  15 complementary Composer interactions and the 15 author cases. Independent
  Standards: **16 executed Composer controls** and a scoped strict typecheck.
  Counts overlap and are not an additional unique-test total.

The first local broad run lacked the workflow file and Git fixture required by
existing tests; the corrected offline run includes them. The first production
build exposed an incompatible Unicode regex literal for the current TypeScript
target; equivalent constructed expressions pass the real build. Initial lint
refused missing API configuration; final lint uses explicit inert loopback values.
These failures were preserved, not counted as successful validation.

## Existing production drafts

The owner authorized preparation of eligible saved drafts, keeping all four
operational controls off. Each existing generated draft was opened through the
actual admin and received exactly one explicit **Refresh caption & hashtags**
command using the existing reviewed endpoint:

| Draft | Saved revision | Actual result |
|---|---|---|
| National CoB report | 1 | `SOURCE_REVIEW_REQUIRED`: current report authority changed |
| KRA catalogue report | 1 | `SOURCE_REVIEW_REQUIRED`: current report authority changed |
| Nairobi pending bills | 2 | `SOURCE_REVIEW_REQUIRED`: current financial evidence changed |

None was eligible for preparation. No revision, caption, destination, tag,
approval or publication was forced through the source hold. The two manual drafts
were left unchanged. Read-only readback confirms all five saved revisions remain
unchanged, with zero targets, publications, media assets, uploads or publish
attempts. The prepared-copy feature is implemented; these legacy production
drafts are **not** claimed upgraded or publication-ready.

Before/after production receipts at 19:07 and 19:24 UTC confirm global/account
publishing false, media false, financial generation absent/default-off and zero
worker/consumer/supervisor processes. Existing scheduled ingestion is separate.
No new hosted run, paid review/model, resource, service, plan or access was added.

The current-source refusals remain part of [#802](https://github.com/Rodgers31/audit_app/issues/802).
This release does not weaken current-job lineage, migrate an old immutable event,
or authorize source adoption/financial generation. Backend source qualification
currently shares the financial-generation flag; separating those controls is
follow-up work so future source acceptance can preserve generation OFF.

This UI change is a reviewed candidate, not a deployment receipt. After merge
and deployment, recheck the actual admin states while preserving the holds.
Private source hashes, executed commands, XML/logs, independent reports and live
refusal screenshots are retained in the task's `draft-readiness-802-20261031`
evidence directory. No personal credentials or raw provider token is included.
