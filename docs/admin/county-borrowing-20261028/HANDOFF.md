# County borrowing checked-scope dates — 28 October 2026

Issue #801 remains open: **zero genuine instrument mappings qualified**. This
candidate adds dated scope disclosures, not a county borrowing balance repair.

The two existing reviewed editions remain unchanged in source identity, bytes,
checksums, pages, scope, reason, stock/report-end date and empty instrument lists.
Their `scope_reviewed_on` annotation is 25 October 2026, the retained B86 review
in `docs/admin/batch86/county_borrowing-source-review.json`. It is the human review
of those specific source scopes, not a fresh provider fetch, publication day or
financial stock date. Changing display annotations does not change the v1 parser
file or expected Extraction JSON and does not silently replace existing receipts.

The existing reader includes that annotation only after its source/extraction
provenance checks. Missing annotations remain null; malformed or future dates
refuse projection. All four county API adapters carry the same fields. The
existing county/home note labels report-period end and source-scope review
separately, with semantic `time` elements and existing citation links. A review
date never fills `debt_as_at`, makes an instrument eligible or creates a zero.
The frontend rejects malformed supplied dates and continues to support undated
legacy citations. This is a small citation-content change using the existing
layout; no redesign or paid design generation was run.

`SOURCE_CHECK.md` records the finite eight-query follow-up and four official
sources. No new edition or mapping was admitted. The retained B86 CoB facility
balances and B103 Meru2023 source are not claimed as new positive discoveries.
The new Nairobi2018 table is a cash-account disclosure, not principal stock;
the Kakamega narrative lacks the explicit contract/issue-date evidence and its
whole report also exceeds the existing combined producer byte cap. Neither
justifies fabricating an instrument or advancing a checksum.

## Separate facility-account contract decision

The retained CoB facility pages can support analysis of a distinct
`reported_facility_stock` account, keyed by publisher account namespace, county,
arm, lender, literal facility label and stock date. It would need reviewed layout
extraction, exact units/currency/basis, immutable byte/page/table evidence,
competing-account and latest-null handling, explicit same-key corrections,
overlap exclusion and source-to-reader tests. Publisher account identity must
never masquerade as an issued contract identity. Repayment arrears, principal
stock, interest costs, employee-loan assets, county receivables, inherited
obligations, proposals/guarantees and pending bills remain distinct measures.

No such contract is implemented or activated here. A decision to expose that
separate measure and reconcile account overlap is still required; it cannot
satisfy `total_borrowing` or all-liability completeness. The instrument route
still requires an actual official contract reference/issuer namespace/exact issue
date linked to dated outstanding principal evidence. Current sources do not
supply that chain. No blanket 47-county or zero-liability conclusion follows.

## Verification and remaining gates

External immutable commands/raw outputs/JUnit/source hashes/interpreter metadata
are under BATCH_116_ORIGINAL_PLAN_SESSIONS/801/engineering. The baseline fixtures
observed 15 failures and one pass, including PostgreSQL-reader and all four HTTP
missing-date assertions. Actual final execution and independent review details
are recorded in the shared TASK-HANDOFF.md and external receipts.

All application execution uses cached OFFLINE Docker with read-only source,
unprivileged UID, private network-none loopback PostgreSQL, no host credentials
or Docker socket, dropped capabilities and bounded resources. The synthetic
fixture migrates the accepted schema and does not qualify production grants.
The cached Python3.12 toolchain is compatibility evidence, not exact serving
runtime parity. The initial Linux Jest attempt failed setup because the retained
dependency tree contains only a macOS native resolver; it is not a product pass.
Actual component SSR/direct controls execute separately. No full application
hydration, Chrome visual acceptance, hosted CI, live source adoption or production
activation is claimed. Chrome remains reserved to the coordinator; qualify the
existing CountyBorrowingNote on the home county panel and County Explorer at
representative widths in a coordinated slot before production UI acceptance.

There are no sibling implementation dependencies or shared authority/generation
changes. The only shared frontend file is the two county-specific i18n keys in
`frontend/lib/i18n/messages.ts`; preserve sibling edits when integrating. #802
owns future generation integration. No source flag, nightly admission/workflow,
schema/grant, credential, setting, billing, production job/backfill, provider
message, deployment/merge, publishing/upload or worker activation was changed.
Keep the PR draft for coordinator/user review. Revert this display change to roll
back; preserve retained receipts, observations, nulls and revision history.
