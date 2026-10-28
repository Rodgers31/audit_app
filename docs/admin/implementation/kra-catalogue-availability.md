# KRA catalogue evidence and mandatory review

Owner decision, 27 October 2026: admit clearly labelled catalogue evidence for
KRA's annual revenue dashboard, while keeping report publication date unknown
and requiring human review. This is an availability announcement, not evidence
of a financial change or a newly published report today.

The native revenue producer may acquire one official catalogue page after
selecting a validated current annual dashboard. The additional transfer is
limited to 512 KiB and 20 seconds. It must bind exactly one result's URL, title,
KRA Revenue Performance category and full entry date to the official wrapper's
annual URL/title and parsed fiscal year. Duplicate entries, unsupported date
markup, redirects, copied receipts, unretained bytes and conflicting scope fail
closed. Missing catalogue authority does not manufacture a report or replace
the independent numeric collection contract.

The retained wrapper and catalogue acquisitions form an immutable current-job
binding. Catalogue evidence uses `evidence_kind=publisher_catalogue`, an explicit
`catalogued_on`, and **`published_on=null`**. It cannot borrow a publication day
from an older article, PDF metadata, a bundle, HTTP headers or retrieval time.
The committed reader performs no source requests. Draft text and the evidence
panel say that the report publication date is not stated. Shadow evaluation
requires human review, and policy scope/admission rejects automatic authority
even if automation is enabled later.

An initial observation establishes a silent baseline. A reasoned explicit
backfill can create one pending-review draft from the genuine current report;
a fresh-command replay creates no duplicate. Reacquiring the same report is not
a new reporting release. Legacy native/CoB publication evidence, serialized
observations, fingerprints, text and release state remain unchanged.

The compressed October 27 primary-source fixtures have a separate hash manifest
in `backend/tests/fixtures/kra/catalogue_2026-10-27.json`. Fixture HTTP/job clocks
are synthetic; they do not attest a production run. Acceptance requires the
native fetcher/parser/writer, migrated PostgreSQL, read-only preview, baseline,
reasoned backfill and independent replay, plus explicit UI evidence inspection.

Rollout: no migration, new login, grant or paid resource. Keep publishing,
uploads, automatic approval/scheduling/publishing and worker activation off.
After reviewed deployment, admit only the selected revenue source, add `kra` to
the existing draft allowlist alongside `cob`, verify the baseline, then perform
the one owner-approved historical backfill and a fresh duplicate check. Stop on
missing/ambiguous evidence, a non-pending draft, extra drafts, or any delivery
attempt. Re-disable KRA drafts if a guard fails; preserve all jobs/evidence.
Code rollback is the previously accepted `fffdfd9d5c33aeccfa5e2392e6876beb7b27e78d`
through the existing Render/Vercel release controls, restoring nightly admission
to that exact source. No publication or deletion is part of this rollback.

Evidence-kind transitions are explicit in durable release state. Catalogue
states have a `publisher_catalogue` discriminator; the exact legacy publication
state schema keeps its original bytes and identifies publication evidence.
Changing kind for the same period is refused in preview and detection, including
explicit backfill. Known publication timing cannot be downgraded to an unknown
day. A later published annual report can follow a catalogue report only when
both period boundaries and its proven publication day are strictly later.
The selected wrapper retains the existing 2 MiB HTML budget; only the additional
catalogue listing has the separate 512 KiB transfer limit.

This closes only the supported KRA catalogue-availability gap. Other #800–#802
source contracts and #699 ordinary worker/provider/cost acceptance remain open.
