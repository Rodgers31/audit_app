# CoB committed-generation qualification

This is selected `actual_spent` producer integration, not authority to publish a
social post. It builds on ETL706 and generation704; the latter's source-event,
immutable-draft and audit schema/service must be integrated before enabling the
post-commit generation hook. No new migration, source service or paid resource
is introduced here.

`SEED_COB_VERIFIED_QUALIFICATION_ENABLED` defaults to `false` and accepts only
literal `true`/`false` configuration values. This separate operator release is
required before **new** county-budget rows can acquire initial verified public
figure eligibility. `SOCIAL_GENERATION_HOOK_ENABLED` and generation runtime
controls remain separate, default-off controls. No configuration is changed by
installing this code; publishing and uploads remain off.

When explicitly released, the existing live PDF fetch/conversion path captures
an unambiguous full date following `Publication date:` or `Published on:` on
one of the first three pages. ISO dates and `1 July 2026` style full dates are
supported. A missing, month-only, malformed, future or duplicate date is refused.
Fiscal periods, PDF creation dates, retrieval timestamps, URL dates and WordPress
media upload dates are never substituted. Existing reports without a supported
genuine publisher-labelled day therefore remain unavailable for this producer;
the implementation does not claim those live reports have been qualified.

The actual PDF bytes must match the intact retained HTTP-acquisition capability.
The date has its exact page/text span and its own sealed parser manifest in the
existing Extraction receipt store. The ingestion-only envelope cannot be
constructed from JSON or restored by pickle; copying retains its original
mutation-detecting snapshot. The writer binds it to the same source URL/artifact
and checks retained-byte readback again before storing date evidence in source
metadata. Unknown retention or date authority does not become a successful date.

After financial row persistence, the writer uses the existing shared
`qualify_rows` actual-spending check over the unique **current ingestion** entry.
The exact record values, entity, period, source, artifact and real PDF-cell
manifest must agree. All historical provenance remains stored; it is not merged
into this one ingestion's proof or replaced by a guessed latest job. Newly
inserted rows alone may initially become eligible. An existing withheld row,
including `publishable=false` without a quarantine reason, is never promoted;
manual quarantine is never cleared. Changing an existing eligible row to an
unrelated source also requires separate review.

With the qualification switch off, unchanged existing eligible rows retain their
state. A writer that changes an existing eligible row's value/source hash,
source-document identity or source artifact instead withholds it with
`cob_changed_qualification_disabled`; new source claims cannot inherit stale
eligibility. Re-enabling the switch does not clear that hold. The job's
`verified_qualification` metadata reports switch state, actual counts and fixed
refusal codes. No fact is relabelled verified solely because it says `official`.

The committed reader uses that same exact-ingestion evidence projection. For
prospective producer date metadata it additionally checks the stored date
Extraction/source/artifact binding. The existing post-commit bridge continues to
separate financial success from generation failure and retains unknown progress
after uncertain late errors. Generated drafts remain `pending_review`; neither
qualification nor semantic detection creates social publication authorization.

Local tests use an actual small valid PDF with ruled cells, the real CoB PDF
parser, retained simulated-response bytes, the actual writer, a newly owned
PostgreSQL17 database and the exact generation704 dependency. They exercise
first-observation baselines, changed evidence, unchanged/replayed ingestion,
history preservation and no SocialPublication. These are code/combined-candidate
checks, not real publisher acquisition, production migration, provider access,
public-post or upload acceptance.
