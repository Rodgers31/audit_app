# Source-disabled refresh qualification — PR #865 review correction

The [high-risk review finding](https://github.com/Rodgers31/audit_app/pull/865#discussion_r4433213304)
is **valid**. The initial gate returned immediately when source admission was
off. National-budget, revenue and county-pending-bills writers replace values,
evidence and current-job bindings on existing rows, so their old
`publishable=True` verdict could survive that subsequent write. Current source
and cell checks still ran, but they did not establish that the new writer job
had source-admission permission.

The initial four-flag matrix covered fresh rows. The independent no-write
flag-toggle control correctly preserved an already admitted source, but it did
not cover an admitted row being rewritten under admission OFF. That coverage
gap is corrected with actual writer transitions across all three adapters.
The original acceptance packet remains unchanged as historical evidence.

## Shared invariant

The shared gate identifies this job's exact native candidates before checking
the source-admission ceiling. For those touched candidates, OFF sets
`publishable=False`, preserving amounts, source evidence, record identities and
all explicit quarantine reasons. A later admitted writer must qualify current
evidence again. Switching the flag off without a write preserves previously
admitted data; the flag is not a reader permission or a revocation operation.

The gate remains bounded to 1,000 distinct ORM rows and deduplicates the cohort.
Invalid/dry-run contexts return without database access. Publisher, official
URL, country, exact source-job binding, exact row-job lineage and county scope
select native candidates; foreign publishers and unrelated scopes retain their
existing numeric-publication decisions. ON continues through the unchanged
measure-specific byte/value checks and explicit-quarantine refusal.

All three writer entry points call this gate after binding current source
evidence in their existing transaction. National and revenue direct writers and
the atomic pending-bills writer therefore receive the same correction. Current
readers, the installed restricted worker witness, report-only authority,
generation ceilings, schema, roles and grants are unchanged. A transaction
rollback restores the old values, lineage, source binding and verdict together.

## Executed regression

Six actual writer cases were observed failing against pushed `1e349292`:
same-value and corrected-value refreshes for national budget, revenue and the
46-county pending-bills cohort. They fail at the inherited numeric verdict,
rather than on imports, configuration or an unavailable database. After the
fix, current readers refuse the rewritten rows, financial dispatch creates no
draft or cursor, and a later admitted write restores verified reading with
financial generation OFF.

Additional repository controls cover no-write flag toggles, explicit operator
quarantine across OFF/ON writes, rollback after invalidation, and both source
states for World Bank rows. The first post-fix fixture correctly refused at a
disabled runtime generation policy before reaching the intended dispatch
refusal; its corrected fixture initializes the owned policy explicitly. The
original failed harness run is retained without acceptance credit.

Final commands, inventories, source pins and independent executable review
artifacts are retained in the [review acceptance packet](native-source-admission-review-20261031/README.md).
All fixtures are disposable, offline and synthetic except the explicitly pinned
retained official contents. Local acquisition/job clocks do not establish new
provider acquisition or production source adoption.

## Operational boundary

Only #864 is authorized and merged in this review round. Its merged tree matches
the reviewed UI tree. The ordinary merge was rejected by branch policy; the
owner explicitly authorized the maintainer override. GitHub rules are unchanged.
Automatic Copilot reviews were read back off. A temporary Vercel ignore-build
hold canceled the merge's automatic Git build; the original empty ignore
command was restored and preview deployments remain disabled. The actual
production alias continues to serve the prior #863 artifact. The project's
latest attempted production target is the canceled attempt, distinct from its
serving alias.

PR #865 remains unmerged and undeployed. No source admission, source ingestion,
database migration, production draft recovery or financial generation is part
of this correction. Publishing, uploads, workers and financial generation remain
off. Existing scheduled ingestion and its admitted SHA are unchanged. No paid
review, hosted test rerun, new resource or service is added. #802 remains open.

The #864 frontend-only merge advances main to `ce352b7`; the exact scheduled
write guard still requires the original `178ff97` approval pin. An offline
execution of that unchanged guard confirms that tonight's scheduled job would
refuse the new main before database access. All changed files are frontend/docs,
so ingestion code is byte-identical. Updating that explicit approval pin is
pending the owner's separate decision; it would admit #864 only, without a
manual run or any admission of the unmerged #865.
