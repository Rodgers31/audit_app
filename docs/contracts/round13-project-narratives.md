# Accepted local project narrative contract — Round14

The owner accepted the bounded local contract on **2 October 2026**. Runtime
implementation covers exactly two retained CoB FY2025/26 narrative anchors,
Nyamira and Siaya, as separate source observations. Round15 also projects the
bounded older Nyamira OAG observation when actual ingested records prove its
artifact and exact evidence context. It does not authorize
production replay, public Projects rendering, automatic OAG corroboration,
aggregate union or closure of [#230](https://github.com/Rodgers31/audit_app/issues/230).
The [comparative examples](round13-project-narratives.examples.json) preserve
an illustrative historical OAG observation; they are documentary examples,
not accepted runtime ingestion records.

The parser, writer and comprehensive county API now carry a separately
versioned optional collection inside the existing **schema-2** county block.
Captioned table rows, their counts and financial aggregates retain their existing
basis. The retained annual replay compares all prior records and public totals
against the initial parser. There are 168 detail rows across 47 county records;
the numeric Table 2.6 county counts sum to 188, its stated total and national prose
say 189, and county summary prose independently sums to 189. These different
bases do not authorize creating rows.

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
| Corpus | `schema_version: 1`, documentary `decision: accepted_contract_examples_only` (runtime `accepted_for_local_implementation`), nonempty `sources`, `evidence`, `observations`; `relationships` may be empty. |
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
“Accepted” here means faithful to the retained source, including uncertainties.
The two CoB annual observations are locally implemented. Round15 additionally
supports the historical Nyamira observation from actual bound ingested OAG
records; the documentary example is never injected into ingestion or API output.

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
remain in the Round12 bank; this implementation does not repeat that search.

| Input/projection | Bounded outcome |
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

## Runtime storage, refusal and API compatibility

`narratives` is optional within `stalled_projects.schema: 2`; the writer's
`_is_current` and legacy-only cleanup continue to recognize old and new blocks.
No schema migration or production replay is implied. A present collection is
an exact-key envelope:

```json
{"schema_version": 1, "status": "accepted", "reason": null, "corpus": "the source-bound corpus object"}
```

A refusal uses `status: refused`, a nonempty `reason`, and `corpus: null`.
Accepted county corpora each have one annual observation, one CoB source, their
own exact retained evidence and an empty relationship list. `schema_version: 1`
is independent of the county block's schema2. The two-anchor validator
re-derives the corpus from bound evidence and requires exact typed JSON
comparison, including source units, dates, measure semantics and all keys.
Structural validity alone never establishes source authority. Documentary
historical examples and arbitrary well-shaped observations are not accepted.

The read projection also requires the surrounding stored source publisher to
match the pinned Controller of Budget publisher; conflicting or missing stored
publisher metadata refuses only the optional narratives. The writer already
assigns that publisher from its owned source contract. This does not infer a
new title rule or suppress existing valid table evidence.

`cob_parser.parse_bounded_narratives` requires the pinned PDF SHA-256,
FY2025/26 annual edition and 935 pages, exact one-based page and county chapter,
county Treasury attribution and following department-section anchor. Only PDF
whitespace and word hyphenation are normalized for comparison; the actual
extracted excerpt, including its line breaks, is retained. Changed or missing
passages qualify only this optional collection, preserving unrelated tables.
All binding constants and helpers remain in the parser's source file, so the
existing content/parser/library-digest cache invalidates their changes.

The writer validates again against the downloaded edition and county identity.
It keeps the existing ordered-lock/refresh/commit boundary, replaces known
edition fields and retains unknown later extension metadata on current blocks.
An older accepted collection cannot survive as an extension when the next
edition has no narratives. Unrelated Entity metadata and route IDs are kept.

`build_stalled_projects_block` returns a qualified `narratives` projection in
both the empty-table and populated-table paths. The comprehensive county caller
passes its canonical name, resolved using official county identity, to refuse
cross-county transplants. Direct service calls may omit that external identity
for backward compatibility; the observation's explicit official county remains
in the projection. Legacy route mappings 047=Mombasa/001=Nairobi are unchanged.

The projection contains `schema_version`, `status`, `reason`, separate
`observations`, `sources`, `evidence`, `historical_identity_candidates`,
`historical_candidate_reason` and `qualification`. Each accepted observation
has `scalar_measures`: a stated measure supplies its value (including explicit
zero); conflicting/absent/unknown/withheld measures supply null. Nyamira paid
has two scoped statements and a null scalar. Siaya has no institution inference,
clamping, loss subtraction or verification label. The table `count`, contracted
value and paid total exclude all narratives. No combined count or national
narrative total is defined, and observations never enter `_link`'s name matching.

Absent optional collections yield `status: absent`, `reason: not_ingested`.
Malformed collections yield `status: refused` with an explicit reason and no
observations, while existing valid tables remain visible. Reasons include:

- `unapproved_source_hash_or_edition`, `missing_page_or_county_chapter`,
  `county_page_context_mismatch`, `missing_bounded_passage`, `changed_bounded_passage`;
- `invalid_narrative_envelope`, `invalid_narrative_refusal`, `invalid_narrative_status`,
  `narrative_source_edition_mismatch`, `invalid_narrative_evidence`,
  `narrative_passage_binding_mismatch`, `narrative_shape_or_source_binding_mismatch`;
- `incompatible_county_block_schema`, `unresolved_county_identity`,
  `narrative_county_mismatch`, `narrative_source_publisher_mismatch`. Invalid nested types/serialization also carry a
  diagnostic refusal rather than an empty accepted collection.

## Round15 artifact identity and historical read contract

`SourceDocument.meta.pdf_artifact_v1` records SHA-256 and MD5 of the actual
PDF bytes, byte size, source document/URL/report/publisher association and the
existing PDF magic/final-EOF validation. It contains no private file path.
Download verification time is recorded only when the downloader sidecar names
those exact hashed bytes and a valid past timestamp; otherwise it is null with
`download_time_not_available`. The existing document cache verification timing
is preserved. A same-byte re-download preserves artifact identity; a changed
edition retains the earlier artifact in `previous_pdf_artifacts_v1`. Unrelated
metadata and later separately versioned keys survive.

The normal county-volume extractor verifies the actual file against this identity
before and after its visible-only page read. Each newly read finding carries
`extracted_json.pdf_artifact_binding_v1`: the artifact snapshot, extractor,
visible-text rule and actual PDF page count. Missing legacy binding remains
absent. The document's latest hash, MD5 extraction stamp, URL/cache filename or
an example cannot backfill it. A future normal complete re-extraction may establish
binding in place; an incomplete reissue cannot relabel older findings.
The loader retains each supported extraction's artifact in Audit provenance.
`Audit.source_hash` remains the canonical extraction-JSON SHA-256, including
binding; it is separate from the PDF-byte SHA-256 and has no self-reference.
Hash-only binding changes preserve stable extraction IDs and Audit references,
while meaning changes/retirements retain the source-reviewed reconciliation gate.
The existing extraction/load transaction rolls bindings back on loader failure.

The comprehensive caller passes the already batched Extraction and SourceDocument
records and requested canonical county to the stalled-project service. The
publishable/display-grade filters remain in place. Historical projection requires
consistent document status/source/type/identity, extraction source/extractor,
canonical JSON hash, Audit source/text/page/entity/period, provenance binding,
visible text, exact chapter/institution and pinned edition/page/paragraph/full
finding-text context. The pinned full-text checksums are refusal guards over
actual visible-text extraction, never documentary records to insert.

Only Nyamira's FY2023/24 Assembly paragraph537 (PDF207/printed193) is accepted
as the primary historical residence observation. Paragraph533 (PDF205/printed191,
continued on PDF206) supplies payable only when it independently passes all guards
and belongs to that same artifact. Missing/ambiguous payable is absent with a
null scalar, not zero. The historical contract/payment/progress/date statements
are derived from the actual bound text. Contract observation date and payable
observation date stay unknown; status/inspection keeps month precision. There
is no source-publication date inference.

The `narratives` projection adds separately sourced `historical_observations`,
`historical_sources`, `historical_evidence`, `historical_evidence_status` and
`historical_refusals`. Candidates use the existing candidate-only decision,
explicit institution/name/commencement-month/rounded-contract/progress comparison
basis and missing ward/shared-tender evidence. Annual fields, table counts and
money totals are unchanged. The old `_link` table matching remains separate and
its existing label is not strengthened. OAG findings gain optional
`artifact_evidence` with available context or an explicit unavailability reason.
No sensitive credential-bearing URL or filesystem path is exported by this
extension.

Legacy direct calls without supplied historical records retain the prior
`ingested_oag_projection_lacks_required_source_hash_and_exact_evidence` limitation.
The actual comprehensive path returns explicit historical unavailability when
required records are absent, malformed, changed or ambiguous; it preserves valid
annual/table evidence. Siaya has `no_approved_historical_candidate_for_county`,
retaining its unknown institution and investigation. An unavailable annual
collection yields `annual_narrative_unavailable` even if older evidence exists.
No historical source example creates an OAG row. Projects remains hidden.

## Evidence and remaining owner decisions

The shipped tests exercise real parser → writer → service/API behavior with
source-shaped extraction-boundary fixtures, decimal/date/type attacks,
refusals, old schema2 blocks, source digest cache reuse/invalidation and metadata
preservation. A separate retained full-PDF replay compares baseline and final
parser records and financial/count projections without downloading sources.
External Round14 receipts distinguish executed checks from prior evidence and
record the PostgreSQL-only skips. SQLite fixtures are not production PostgreSQL
persistence/concurrency acceptance.

Source clarification for Nyamira's annual paid conflict, definitive historical
identity and Siaya institution attribution remain external inputs. Root owns
any separately authorized legacy cleanup, production provenance/API/rendered
acceptance, language review and final Projects exposure decision. Keep #230 open.
