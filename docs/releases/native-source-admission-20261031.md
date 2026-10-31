# Native source qualification with financial generation paused

Work for [#802](https://github.com/Rodgers31/audit_app/issues/802), based on
`178ff97d8a593ed8a152366cfdb446a29b434a45`. The existing source writer used
`SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED` to decide both whether to qualify
native monetary cells and whether to generate financial drafts. That coupling
prevented independent source acceptance while the owner kept financial
generation off.

## Independent controls

`SEED_NATIVE_FINANCIAL_SOURCE_ADMISSION_ENABLED` is a new **default-off**,
process-wide ceiling. Only the exact string `true` permits prospective numeric
source qualification. Missing, ambiguous, nonstring and truthy malformed values
do not admit it. A caller's settings object or serialized source payload cannot
grant this process permission.

| Source admission | Financial generation | Result |
|---|---|---|
| Off | Off | No newly qualified numeric rows; no financial generation |
| On | Off | Verified newly bound native cells may qualify; financial generation remains disabled |
| Off | On | No new source qualification; any generation still needs previously qualified current evidence and all existing gates |
| On | On | Source and generation each retain their separate evidence, runtime and review gates |

The source ceiling is used by the shared qualification gate and by national
budget/pending-bills fresh parsing. An admitted non-dry-run job candidate
cannot obtain financial cell authority from cached normalized JSON. Dry runs,
missing/invalid job identities, retained aging and ordinary cache behavior keep
their existing boundaries. All three monetary writers use the shared gate.

The workflow binds the new repository variable with a literal `false` fallback.
No repository variable is created or enabled by this change. Ordinary bounded
admin qualification requires the new source ceiling off as well, alongside its
existing paused controls.

Source admission does not enable a generation hook, approval, schedule, worker,
provider adapter, upload or publication. Report generation keeps its independent
existing controls. No generation, renderer, current-authority view, role, grant,
schema or monetary calculation is changed. Current successful-job lineage,
retained bytes/cells, publisher identity/date, chronology, quarantine and
financial evidence checks remain mandatory.

## Source acceptance and limits

The regression executes the real KRA-shaped producer, writer, PostgreSQL
qualification and committed reader in all four control combinations. The old
source produced two wrong outcomes: generation off blocked otherwise admitted
source qualification; generation on qualified new cells without independent
source admission. Those two cases failed on the pre-fix code while the other
two passed, then all four passed after separation.

The source-only positive path also runs with the global generation hook on and
the financial ceiling off: source reading passes while financial dispatch is
disabled and creates no source cursor, post or publication. Retained KRA FY2025/26
catalogue bytes remain report-only, with publication day null and every numeric
row held; the new source switch cannot convert a catalogue date into financial
authority. Foreign-source eligibility and explicit quarantine retain controls.

Supplementary retained-input checks use the genuine CoB FY2025/26 annual PDF
and exact publisher post, and the dated original KRA FY2024/25 article. The
complete national producer verifies ten rows/twenty cells through PostgreSQL
and the current financial reader on fresh parsing and retained reacquisition;
all twenty stored values and record identities remain equal. The dated KRA
article also passes the actual producer/current reader and reacquisition.
Financial generation stays off throughout those producer/dispatch operations,
with zero social cursors, posts, targets or publications.

These are genuine retained **contents** with local transport/acquisition/job
clocks and an owned database, not new official acquisitions, production
adoption or current-fiscal-year KRA acceptance. The national source work fits
the unchanged 512 MiB local test cap. Missing publisher dates and unsupported
source contracts remain refusals.

Executable replays, required input hashes and final verification counts are
recorded in the [acceptance packet](native-source-admission-20261031/README.md).
The affected selection passes 664 cases in each Python mode, with zero
failures/errors/skips. The genuine pipeline adds three cases in each mode.
Independent Spec (146 per mode) and Standards (30 per mode) pass; their counts
overlap with repository corroboration and are not added to a unique total.
Input bodies are retained
outside the public repository; missing inputs must fail rather than skip.

## Rollout boundary

This is engineering acceptance, with source admission, publishing, uploads,
workers and financial generation held in production. No production source
ingestion, draft replacement, source adoption, flag enablement or hosted rerun
is performed by this change. Existing scheduled ingestion and its admitted SHA
are unchanged. No paid resource, plan, grant, model or review is added.

After a separately reviewed merge/deployment, an explicitly bounded source-only
admission can validate current production rows while financial generation
remains off. Pin the source/deployment, select exact domains/jobs, retain before
and after row/value/qualification/source receipts, and restore the original
source ceiling afterward. Turning admission off stops prospective qualification;
it does not erase already accepted factual data or reverse its eligibility.
Data adoption needs its own reconciliation and rollback boundary.

The three old production draft preparation attempts remain correctly held on
stale source authority. This change does not rebind their immutable events,
inherit old approval or relabel them prepared. Use the existing explicit current
source/reasoned recovery path only after the relevant source is actually
accepted. #802 and the broader launch gates remain open.
