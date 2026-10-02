# Round14 coordinator verification — 2 October 2026

Two completed GPT-6.1 Sol/high sessions were consolidated from exact base
`748eea8e0d67f1a8a2337d18fe692d803455d820`:

- Debt commit `ada6b43d6ca12ca46f23dda4c9b27063c95a5df4`, tree
  `861651cc94b41f75f5f3d21bfeac20d82032f734`.
- Narrative commit `286e3765a9d036152653a713d0d48a45d355f935`, tree
  `7fe499996934efbdc1473930e0f1ec3684ed118e`.
- Coordinator publisher fix `2b9246f1e78eef5d7b370396759939bf0cbc565e`.
  Tested backend subtree: `18f59c0ce05ede54972d500c56dddf52c9e98c56`.
  Frontend and workflows are unchanged from the base. Later receipt-only edits
  do not change this tested runtime subtree.

## Executed coordinator evidence

`ROUND14_COORDINATOR_BACKEND_RUN.py COMBINED_FINAL` ran the actual debt
parser/writer/domain, project parser/writer/service/API, cache and county identity
controls: **431 passed, zero skips**, exit0. It selected15 files, including the
seven coordinator publisher regressions; its log records application-engine
connection attempts0. Settings used an allowlisted child environment, disabled
dotenv/Pydantic env files, synthetic psycopg2 loopback55523, test/env secret backend,
empty Redis, disabled warmup/seeder, inert lifespan and refused unstubbed HTTP.
Tests use SQLite; this is not production PostgreSQL/concurrency acceptance.
Critical flake8 and `git diff --check` passed.

The first combined run was417 passed/7 failed: a copied launcher disabled PDF
fetching, blocking tests whose actual network/PDF boundary is mocked. That test
configuration was corrected without weakening HTTP blocking. It was not an
application regression or a passing run. No output was overwritten.

Root recomputed47 source/file/artifact hashes, including both retained PDF banks
and the exact Nyamira/Siaya text excerpts in the shipped fixture. Session2's
retained full-PDF execution is inherited, not rerun by root:47 county records,
168 detail rows,188 numeric Table2.6 county counts,189 national stated count and
189 county-prose count; old parser/writer/public totals matched after removing
only optional narratives. Source bytes:

- CoB: `5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`.
- Documentary older OAG:
  `683fa522bf11eaa2b0bc2a9eef51eadc3d664d9a512d3af63cb6e9479820f8a2`.

Independent debt review executed12 final controls, with8 failed/1 passed against
the baseline: invalid later batch before SQL/mutation, generated-title collision,
promotion/metadata, malformed inheritance and real CBK/IDS producers. No further
defect was reproduced. Worker142 tests and its98 reviewer controls are separate
executions and overlap these coordinator tests; counts must not be added.

Independent narrative review executed hostile source/period/page/county/number/date
and malformed-input cases, actual SQLite comprehensive routes, cache invalidation
and metadata-preservation controls. It found the publisher issue below. Its
initial typo and overstrict title assertions are disclosed in the external
receipt. Session2's201 passed/104 PostgreSQL-only skips,81 compatibility tests,
68 hostile controls and one retained-PDF replay remain distinct inherited runs;
skips are not passed persistence tests.

## Findings and decisions

**Valid, fixed under #230:** a valid CoB corpus could be accepted while surrounding
stored `source.publisher` claimed OAG. Root reproduced through writer/service
and the real comprehensive API, then ran seven repository regression cases red.
The projection now requires the pinned CoB publisher, refusing only optional
narratives while preserving valid tables and totals. The final combined run is
green; independent post-fix canonical/wrong/missing/API controls passed4/4.
Writer publisher canonicalization is unchanged.

**Outside the approved narrative contract:** a forged top-level source title
survives the old writer/service metadata path, including the comprehensive API.
The real parser always emits the canonical CoB report title, and the approved
corpus schema has no title field. An initial reviewer refusal expectation was
stronger than that contract; it is not a demonstrated new parser/producer bug.
This inherited stored-source labeling limitation is recorded with #230's
publication acceptance, without inventing a broader title heuristic.

Worker-discovered cross-county transplant, numeric hyphen, deep optional evidence,
debt display-title collision/promotion and Unicode identity cases were reproduced,
fixed and covered within #230/#274. No distinct unfiled application defect was
established; no duplicate issue is warranted. Historical OAG candidates remain
explicitly absent because the current read projection lacks required hash/exact
evidence. No documentary OAG row, automatic join, combined project count, loss
inference, financial-total change or public Projects exposure was introduced.

## Closure and release boundary

All19 open issues were reread with current bodies/comments. #274's local identity
prevention and #230's bounded narrative implementation are complete, but their
stored correction/source/public acceptance requirements remain. No parent issue
is wholly closable from this round; completed checkboxes and remaining inputs
must be updated accurately after merge. Umbrellas #137/#322 retain their linked
source/history/schema/production acceptance; no artificial closure is inferred
from local tests.

Actions stays OFF. No provider credentials, production database access,
configuration/secret/signing/cache call, seed/migration/correction/cleanup/backfill,
new source download or paid review occurred. The dirty primary checkout was
preserved. Protected documents1823/2541, population79, existing project arrays,
later metadata and routes047=Mombasa/001=Nairobi were preserved in local controls.

Production work still needs fresh exact plans, writer coordination/freeze, a full
consistent backup with successful isolated restore, recovery review and the
separate final action approval. Next high-priority work is actual stored/public
data acceptance, provider readiness and source/human inputs; code preparation
alone cannot close those issues. The OAG narrative evidence projection can be
extended locally using actual ingested records and qualified candidate-only
identity, without another fetcher or exposing Projects.

External receipts are retained beside the Round14 briefs: session handoffs,
`ROUND14_COORDINATOR_COMBINED_FINAL.log`, `ROUND14_COORDINATOR_PUBLISHER_RED.log`,
`ROUND14_COORDINATOR_HASH_VERIFICATION.json`, debt/narrative review receipts and
`REVIEW_FIXED_RECEIPT.md`. These are scoped test receipts, not a new public census.
