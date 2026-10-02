# Round13 coordinator review — 2 October 2026

## Disposition

All four authorized coding/observation sessions completed without task errors.
The county and KRA patches are consolidated in [#440](https://github.com/Rodgers31/audit_app/pull/440).
The project contract and examples are a proposed maintainer decision, with no runtime integration or Projects exposure.
The release session delivered a dated observation and no patch.

Reviewed worker identities:

| Lane | Local commit | Tree | Deliverable |
| --- | --- | --- | --- |
| Project narrative contract | ec59978ebf7ee487229f62969b507ce90e1bf416 | 83f363c21b408ca93981e4ee9758a45dc9622303 | Two proposal documents, 637 lines |
| County cash qualifications | 434906766eabb61c982a9e1b99e8e83208c02033 | cbc2051f470fef7b8183f5ed37f3d16d8c6d2292 | Existing reader, optional API annotation and two existing card consumers |
| KRA qualifications | 012d03a75f8430d9aa6bce656a14e97211927999 | 90f5ae17590b1f0306f4d03cb1aab126aee92e40 | Existing enhanced API source reason and RevenueMix rendering |
| Release observation | c71666b7d29dceffa3f684ed3c9a4db03bbded0d | 680cb3a348a4e071187d1e4d4280c9abb2f5e977 | Clean worktree; nine read-only captures |

The combined runtime head is e283521c230dbc811d93bebb8e2e4b10f2c79f84,
tree 51ce280d152221e1dfca9e9ff79dec8f2a78d530.
No configuration, migration, ingest, correction, signing, cache refresh, amount selection or source preference is changed.

## Accepted behavior and discoveries

County cash refusal annotation requires one KES budget Total, linked source/period,
official matching source title, coherent coverage history and a valid artifact digest
equal to the current linked document digest. Missing, malformed, stale, conflicting
or incompatible evidence retains qualified generic absence. Existing cash errors
are not replaced by old coverage; partial cash and measured zero remain distinct.
The API passes reason, source pages and period to the existing adapter and
OverviewTab/FinancialOverview consumers. Unknown diagnostic codes use generic
localized prose. The six new draft Swahili keys are in the [human review supplement](2026-10-02-round13-county-language-review.md).

An independent worker reviewer reproduced a real same-URL correction state: the
Kwale Total retained artifact A while the shared SourceDocument carried artifact B
after a Migori correction through the actual existing writer. The proposed reader
initially misattributed the refusal. Digest equality now refuses that attribution,
with matching/missing/changed/malformed route regressions. This introduced finding
was fixed before the worker commit. The inherited discarded-refusal publication
gap belongs under #299; no duplicate ticket is needed.

KRA edition, source period, retrieval, unknown publication date and reconciliation
remain visible independently of a missing/unsafe link. API missing-URL wording
does not erase an already recorded edition/date and recognizes existing data_url
presence; frontend links still require HTTP(S). Monetary serialization and
amount/FY/series/YoY/filter calculations are unchanged. These three inherited
qualification gaps belong under #298. Synthetic malformed publication dates do
not establish a current producer defect: both current source paths emit null.

The [project contract](../contracts/round13-project-narratives.md) keeps narrative
observations separate from existing detail arrays and aggregate money/counts.
Nyamira's 26.65 million named paid statement and 26.62 million county-singleton
summary remain a scoped conflict. Siaya's 1.88 million value and 3.72 million paid
remain publisher-attributed investigation, with unknown implementing institution.
Historical OAG contract, paid, payable, progress and dates remain distinct; an
identity candidate grants no current verification or loss conclusion.
Existing 168 detail rows / 47 county records and 188 observed versus 189 stated
summary counts remain protected. The source-bound external validator is a bounded
prototype, not an unused runtime validator. #230 remains open.

No remaining independently confirmed new application defect was found by the
coordinator reviews. Discoveries are recorded on existing #299/#298; narrative
follow-up remains #230 and language review remains #307/#372.

## Executed verification

Counts overlap across authors, independent reviewers and coordinator. They are
reported by execution scope rather than added together.

| Executor | Actual result |
| --- | --- |
| Coordinator combined branch | 95 backend tests, no skips; configured database connection attempts 0 |
| Coordinator combined branch | 58 frontend tests / 6 suites, no skips; source-bank actual API → adapter → both card consumers |
| Coordinator combined branch | Full TypeScript and focused ESLint, exits 0; whitespace check exit 0 |
| Coordinator county reviewer | 12 independent states, preserving all previous money fields versus exact base reader; 56 recorded artifact hashes and HTTP/renderer snapshot equality checked |
| Coordinator KRA reviewer | Exact five-file diff and actual producer/callers; 39 artifact hashes, no mismatches; no concrete gap justified additional runtime probes |
| Coordinator contract reviewer | One source-bound corpus and five targeted refusals; two retained PDF hashes and three retained text hashes recomputed; exact document byte checks |
| County author / worker review | Final 58 backend / 18 frontend; independent 93 hostile backend / 19 frontend, with overlap excluded |
| KRA author / worker review | Final 45 frontend / 4 actual API; independent 48 renderer / 35 actual API, with overlap excluded |
| Contract author / worker review | 6 positive / 43 refusal controls; 174-case final review with no expected-refusal false successes |
| Coordinator observation check | Nine owned captures, 25 owned artifact hashes and 40 Git object pairs verified offline |

Backend launcher used an allowlisted environment, disabled dotenv/Pydantic file
loading, synthetic signing, test mode, inert lifespan, seed/warmup off, Redis empty,
and configured psycopg2 target 127.0.0.1:55515/round13_coordinator whose connections
were forbidden. All database fixtures were isolated SQLite. Outbound provider/app
HTTP was forbidden except in-process Starlette transport. Frontend used explicit
SWC config, loopback API destinations, telemetry off and forbidden fetch/XHR/socket.
Existing runtimes/dependencies were reused; no install, PostgreSQL, container or
app server was started. Three exact owned probe/dependency links were removed;
shared targets were preserved.

These executions establish local behavior, not PostgreSQL transaction parity,
fresh stored source coverage, deployed configuration, browser layout, nightly
acceptance or competent language accuracy. Prior full source replay/PostgreSQL
results are inherited. Early worker setup failures and the fixed temporary
TypeScript probe are disclosed in their handoffs; final production files passed.

## Dated deployment observation

At 2026-10-02 04:07 UTC (1 October 23:07 CDT), the backend health response reported
RENDER_GIT_COMMIT prefix 6377e2ad6fc0. The locally unique candidate is #437's merge
6377e2ad6fc041c779e6197c465467a8f3810a20; backend/scripts/tools/.github Git objects
equal the then-current main c71666b. This proves reported marker/code equivalence,
not a full provider image/revision or settings/schema proof.

The sampled homepage marker dpl_DMHvZcVCFFdVYRL3tA6qJAnSAYHy matches the successful
Vercel status bound to GitHub deployment6800635596 at c71666b. Homepage body SHA256:
94c00e08f4abd857775a910ebbede7ed8ef48c1e0b9cae6b3569df27315cf8a4.
This binds one sampled homepage deployment; it certifies no new data transition,
tooltip runtime, every page or the newer Round13 patch.

Latest seed run remained36660207026 (30 September), with seven jobs and zero
recorded steps. Earlier billing annotations are inherited, not fresh account-balance
proof. No newer seed execution or fresh seed→validate→API invalidation→frontend
acknowledgment→changed rendered page was observed. #231/#378/#322 remain open.

## Issue closeout and release

All 19 remaining issues have source, history, human or actual production/final
acceptance criteria outstanding. No issue is fully closable solely from these
local changes. Actions remains OFF; no workflow or billable reviewer was dispatched.
Owner-authorized admin merge may bypass the expected disabled Actions checks after
local verification. A merge does not authorize production data/configuration writes.

Use the existing [correction and recovery packet](../operations/2026-10-01-round11-correction-readiness/README.md)
and [five-volume OAG packet](../operations/2026-10-01-round11-oag-catchup/README.md).
Fresh exact before-images, writer freeze, full backup with isolated restore,
recovery review and separate final action approval remain required before writes.
Preserve documents1823/2541, population79=51,202,827, current project arrays/later
metadata and legacy routes047=Mombasa /001=Nairobi.

After adoption, target existing refusal reasons/source pages, recovered Kisii,
Mombasa cash versus summary and KRA qualifications in actual rendered acceptance.
Abort an introduced amount/qualification/rendering regression; code rollback is
a separate reviewed revert of #440's squash commit, with no stored state to unwind.
Detailed local receipts/scripts are retained in the Round13 handoff directory.
The coordinator fresh issue fetch superseded an old external issue-list cache;
that inherited cache hash is not recertified. Owned observation captures match.
