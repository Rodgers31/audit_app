# Proposed project narrative contract — Round13

**Maintainer decision proposed:** accept named narratives as a separate collection
of source observations, with no automatic projection into project detail rows,
counts, financial totals or OAG verification. This document and the
[source-bound examples](round13-project-narratives.examples.json) are a review
proposal for [#230](https://github.com/Rodgers31/audit_app/issues/230), not an
approved runtime schema, ingestion instruction or permission to expose Projects.

The current parser reconciles captioned detail-table rows
(`backend/seeding/domains/stalled_projects/cob_parser.py:1137–1142`); the writer
constructs its `rows` from those tables (`writer.py:212–220`). Narrative support
would extend that scope. A dropped table row has not been demonstrated.
[Round11](../verification/2026-10-01-round11-county-source-reconciliation.md)
retains 168 detail rows across 47 county records, 188 observed summary counts
and a stated 189 total. Those inherited cardinalities have different bases;
189−168 is not authority to create 21 records. No parser, writer, stored array,
metadata, service, exposure gate or source acceptance changes in this proposal.

## Terms and minimum schema

A **narrative observation** is one publisher's account of one exactly named
project in one edition, attributed to a county and, only when explicit, its
implementing institution. It is not a globally resolved project identity.
A **statement** is a typed measure with its own scope, source locator and
observation date. A **historical identity candidate** relates two observations
for human consideration; it does not merge their values or verify current status.

Version 1 is a strict JSON object. Unknown keys and wrong containers are refused.
All fields below are required, even when their content is absent. The examples
are a small source-bound corpus, not permission to ingest every narrative.

| Object | Required content |
| --- | --- |
| Corpus | `schema_version: 1`, `decision: proposed_for_maintainer_review`, nonempty `sources`, `evidence`, `observations`; `relationships` may be empty. |
| Source | Official PDF URL, SHA-256 of retained bytes, positive integer page count, fiscal year `YYYY/YYYY`, scope `annual` or `audit_year`, publisher. Cover month and website publication/download dates are edition metadata, never observation dates. |
| Evidence | Source reference, one-based PDF and printed page, paragraph string or explicit `null` for unnumbered CoB prose, nonempty section anchor and exact retained excerpt including line breaks. Paragraph plus source/page is a locator, not an invented OAG case ID. |
| Observation | Opaque local `observation_id`, official county code/name, exact `name_as_printed`, `location`, `reporting_body`, `implementing_institution`, `tender_reference`, source reference, fiscal year/scope, named evidence reference, five measure slots, milestones, status. |
| Text field | `{state, value, reason}`. `stated` has nonempty text and null reason; `absent`, `unknown` or `withheld` has null value and a nonempty reason. Institution is one institution or unknown, never an array or an inferred department. County code is governance identity; legacy routes 047=Mombasa and 001=Nairobi are not rewritten. |
| Measure slot | `{state, reason, statements}` for each of `estimated_value`, `contract_sum`, `paid`, `payable`, `completion_pct`. `stated` has one statement; `conflicting` has at least two different values for this measure at a common known observation date/precision, and a reason; other states have an empty list and a reason. No scalar winner alongside a conflict. |
| Statement | Nonnegative finite numeric `value`, normalized `unit` (`KES` or `percent`), exact decimal/comma `source_value`, source unit (`KES`, `KES_million`, `percent`), evidence reference, scope (`named_project` or `county_summary_one_project`), `as_of`. Money is integer KES in v1; progress is finite 0–100. Booleans are not numbers. |
| Date | `{value, precision, reason}`: real ISO date for `day`, `YYYY-MM` for `month`; `unknown` has null value and explicit reason. Never pad a month to a made-up day. Each statement retains its own date; source fiscal year does not fill an unstated date. |
| Milestone | Kind `commencement`, `expected_completion` or `inspection`, date and evidence reference. A contract commencement is not a payment observation date. |
| Status | Classification `reported_stalled`, `under_investigation` or `historical_value_for_money_concern`, evidence reference and date. Preserve the excerpt as the publisher's words; no proven-loss measure or current-audit boolean exists in v1. |
| Relationship | From/to observation IDs, type `historical_identity_candidate`, explicit comparison basis and missing identity evidence, decision `candidate_only_no_automatic_join`. An empty relationship list asserts nothing about corroboration. |

`absent` means the bounded source passage does not state that field; it is not
zero or proof of exhaustive absence. `unknown` means attribution, identity or
observation date cannot be resolved from that evidence. `withheld` means the
source assertion cannot safely be normalized/published: keep the raw excerpt
and reason, with no numeric statement. `conflicting` preserves incompatible
assertions on the same period/measure/date without deciding which is true.
Different dates or periods remain separate observations, not a conflict to
reconcile. An explicit numeric zero remains a
`stated` zero, with source evidence; it must never replace any of these states.

Structural validity is necessary, not source acceptance. A source-binding check
must resolve every reference, check hashes and actual page/paragraph/excerpt,
verify county/institution/name against the passage and its chapter context,
prove unit conversion with decimal arithmetic, and retain period and measure
semantics. A correctly shaped invented name or a paid value relabelled payable
must be refused. A schema cannot itself establish these facts. Version 1 has no
fuzzy name join, unit-magnitude heuristic, institution default or OAG reference
fabricator. Do not silently skip malformed observations in a success verdict.

## Concrete accepted observations and refusals

The examples contain three observations, sourced from the
[Round12 comparison manifest](../verification/2026-10-01-round12-project-scope-corroboration.json).
“Accepted” here means faithful to the retained source, including uncertainties;
it does not mean approved for public integration.

- **Nyamira annual:** CoB SHA `5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`,
  PDF686 / printed652 / unnumbered named paragraph. County Assembly Speaker’s
  Residence, Bonyamatuta Ward; reporting body Nyamira County, implementing
  institution Nyamira County Assembly, February2023 commencement,
  estimated KES34,380,000 and 77% as at 30June2026. Preserve paid
  KES26,650,000 in the named paragraph **and** KES26,620,000 in the preceding
  singleton county summary. The latter is county-scoped, not another named
  project assertion. Comparing it to the sole named project is explicit in
  `county_summary_one_project`; it neither creates a second project nor makes
  an unqualified value. Table2.6 PDF45 / printed11 also says 26.62 million;
  it remains the existing county aggregate, not a new project statement.
- **Siaya annual:** same CoB SHA, PDF758 / printed724 / unnumbered paragraph:
  completion of Nyamonye Juakali, Yimbo East; value KES1,880,000, paid
  KES3,720,000, under investigation as at 30June2026. Reporting body is Siaya
  County. Implementing institution is **unknown**: neither county reporting
  nor nearby departmental table rows identifies it. Retain paid > value; do
  not clamp, subtract to invent loss, or label it OAG-verified. National prose
  PDF45 describes overpayment, which remains a publisher statement.
- **Nyamira historical:** OAG FY2023/24 Assembly SHA
  `683fa522bf11eaa2b0bc2a9eef51eadc3d664d9a512d3af63cb6e9479820f8a2`,
  PDF207 / printed193 / paragraph537. Contract KES34,377,805;
  commencement6February2023; expected completion6August2024;
  28May2024 status report 77% and paid KES24,158,208; September2024 inspection
  and value-for-money concern. Paragraph533, PDF205 / printed191, separately
  states KES2,457,540 payable; its exact observation date is unknown in the
  retained passage. Contract sum, estimated value, paid and payable stay
  distinct. Older paid + payable =26,615,748, rounding to26.62 million, does
  not prove that the payable became paid or resolve the annual conflict.

The historical candidate's institution/name/start month/rounded contract/progress
align, but paragraph537 supplies no ward or shared tender identity. Keep it
separate and explicitly older-period. OAG FY2024/25 paragraph621 carries an
unresolved prior issue without fresh residence money; paragraph632's
KES367million offices block is another project. Siaya's Nyabera Primary School
ECDE block (paragraph1134) is another name and period. Neither can supply a
Nyamonye institution, OAG match, payment or loss. Their exact identities/locators
remain in the Round12 bank; this proposal does not repeat that search.

| Input/projection | Proposed outcome |
| --- | --- |
| Siaya institution explicitly unknown with reason | Accept observation; no institutional join. |
| Missing institution key or inferred “Executive” | Refuse, even if the rest is well-shaped. |
| Both Nyamira annual paid assertions | Accept as conflict; public scalar paid stays null if later approved. |
| Selecting 26.62/26.65, replacing either with 24,158,208, or adding paid + payable | Refuse as source resolution/current paid value. |
| Assembly and Executive observations with the same name | Keep distinct; institution mismatch refuses an identity link. |
| Same tender-looking token without issuer namespace/explicit source binding | Refuse definitive identity; v1 offers only a qualified candidate. |
| Old value-for-money concern | Accept historical attributed concern; refuse “proven loss” or current audit verification. |
| Empty/malformed payload, wrong schema, bool, NaN, infinities, negative money/progress or progress >100 | Refuse visibly, without empty-success fallback. |
| Explicit source-backed zero versus absent/withheld/unknown/conflicting | Preserve stated zero; refuse coercion of any missing state to zero. |

## Coexistence, counts and bounded next implementation

If the maintainer accepts this contract, add a separate versioned `narratives`
collection inside a future county block, leaving `rows`, table evidence,
`summary`, `table_2_6`, reconciliation, withheld fields and later metadata intact.
Do not append to today's detail arrays or reuse their public `count`/money totals.
Expose separate narrative-observation cardinality only after a separately
approved service contract; multiple statements and an older observation are
not distinct projects. A named narrative that may overlap a detail row needs an
explicit reviewed identity mapping. Unresolved overlap means no combined count,
no union-by-name and no narrative-derived national total. Extraction cardinality
zero remains separate from a publisher's reported count of one.

A future plan, requiring authorization before implementation:

1. Maintainer accepts/revises the five state meanings, separate collection,
   singleton-summary comparison scope and candidate-only OAG relationship.
   Decide whether public rendering may show unresolved/unknown observations,
   labelled as such; conflict scalars remain null. No exposure approval follows
   merely from approving a storage contract.
2. Implement only the two known CoB named passage anchors in the self-contained
   parser, under the edition hash/period boundary and its parser-digest cache
   invalidation. No universal narrative heuristic. Tests first: exact passages,
   both paid statements, absent institution, source revision/wrong edition,
   unknown overlap and corrupt shapes; run genuine red/green controls.
3. Extend the writer with an explicit schema/version decision and preservation
   tests under its existing locked transaction. Preserve every existing row,
   cash refusal, source array, unrelated/later metadata and legacy route mapping.
   Define migration/read compatibility before any write; no production replay,
   seed or cache refresh follows from local tests.
4. Independently review a narrow service projection. Use existing OAG ingestion
   records, never a second fetcher or a fuzzy automatic join. If historical
   candidates are exposed later, show source fiscal year, actual observation
   date and identity uncertainty; never `oag_verified` for current CoB values.
5. Obtain exact source clarification for the annual paid conflict and any
   definitive identity/implementing-institution claim. Coordinator separately
   handles authorized cleanup, production provenance/API/rendered acceptance,
   competent human review and final Projects exposure approval. Keep #230 open.

This session executes only an external source/schema example validator and
adversarial controls. Prior full-PDF extraction and application tests are
inherited evidence, not rerun or production certification. The exact scripts,
results, independent review, commit/tree and cleanup are recorded in
`ROUND13_SESSION_2_HANDOFF.md` beside the Round13 briefs. No fresh public request,
PDF download, application import, database connection or runtime patch is needed
to make this contract decision reviewable.
