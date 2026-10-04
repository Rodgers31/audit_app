# CI literal guards: exact source-context review

Base: `6e3936d139c1d798e47bd80c2cd3f1609ee9fcf8`. Author branch:
`codex/remaining-ci-safeguards`; the original API author branch is preserved.
No source quantities, publication guards, scan roots, detector rules, positive
controls, inventory signatures/dispositions/tracking issues or production data
were changed. No ticket was reopened. This fixes the actual all-tree safeguards
rather than importing the root's first-five failure summary as exhaustive.

## Reproduction and additional finding

The two all-tree county/finance suites executed red: **6 failed,843 passed**.
Five reported findings reproduced; the sixth was full-AST inventory drift in
`tools/verify_sourced_record_cleanup.py`. A SQLite URL initially failed at
conftest import because production engine pool settings do not support SQLite's
SingletonThreadPool. The actual red run used an explicit inert local PostgreSQL
engine URL; these source guards do not open that database. No provider DB credential was used;
.env files were not inspected. Tests keep the repository's outbound-network guard.

## County selections: three exact inline reasons

| Literal | Actual source/caller evidence | Classification and scoped correction |
|---|---|---|
| Nyamira/Siaya inside `_narrative_corpus` | `NARRATIVE_SOURCE` pins the complete FY2025/26 CoB PDF SHA256; `NARRATIVE_EVIDENCE` pins p686 and p758 passages. `parse_bounded_narratives` verifies edition, pages, chapter bounds and exact excerpt equality before calling the corpus builder. `validate_bound_narratives` rederives that corpus and refuses changed identity, evidence or measures. Writer and API consume that validation. | Two accepted narrative-source anchors, not a performance ranking. Add existing `counties-literal-ok` reason only beside the set literal; no module exemption. |
| Six `RECOVERED` counties in cash adoption tool | Complete935-page source hash, full47-county producer payload hash and parser hash are checked; source/FY identities, exact37-accepted baseline, missing six/four sets and complete replay values constrain `build_plan`. Round21 closure validation records these six as the approved40-row cash adoption plus six Total-provenance updates, preservation and inverse controls. | An exact already approved operation cohort. Annotate only this literal; source amounts remain parser-produced and protected. |
| Four `WITHHELD` counties in same tool | Full producer coverage must equal this refusal set; it is excluded from accepted/recovered scopes. Existing cash source contradiction/incomplete-cell outcomes remain. | Explicit source refusals, not a ranking. Annotate only this literal; no upgrade, scope change or re-adoption. |

The parser comment changes its whole-file cache digest, as expected for this
parser's established invalidation mechanism. It does not change parsed values,
source bytes or evidence matching. Actual parser/cache and hostile source tests
passed. Adoption-tool changes are comments only; no financial AST changed.

## Social duration

`READ_BUDGET_WINDOW_SECONDS=86400` has exactly one runtime load, passed as
SQL `make_interval(secs => :seconds)` to the target's rolling read-attempt query.
It admits at most100 poll/reconcile intents per24-hour window, including missing
results; upload/mutation history is excluded. `claim_next` and
`read_budget_exhausted` consult this window. This is request admission/time,
not a measured public-finance quantity. Rename it to
`READ_REQUEST_WINDOW_SECONDS` at definition and use;86400 and all query/runtime
behavior remain exact. No scanner exception was added. The complete isolated
PostgreSQL queue suite passed64 tests, including exhausted-window recovery,
unfinished read intents, exclusion of old/mutation history, concurrency,
restart and crash controls. Its fake adapters perform no real publication.

## Every affected reviewed-finance site

The source at previous inventory commit `355c057` was loaded with `git show`.
Its complete module AST hashes match the prior pins for **all three** drifted
modules. Both old and frozen current main/provenance modules were run through
the raw detector:4 and3 findings respectively, with identical signatures and
values. The cleanup tool retains its one synthetic-count finding. All eight
sites below were reread with current callers and module differences before the
pins were updated; no blind hash refresh or new finance acceptance occurred.

| Site / literal | Current use review against pinned prior code | Disposition retained |
|---|---|---|
| main `_MAX_COUNTY_BUDGET_KES` /50000000000 | Tree search finds definition only; no production load or clamp. No new use. | Unused contextual upper bound; raw finding remains, #301. |
| main `_PENDING_BILLS_SEVERE_SHARE` /25.0 | Two production loads in `county_financial_health`: score scaling and disclosed zero-at25% basis. The entire helper AST is identical to355c057; observed pending-bill share remains computed from supplied amounts. | Explicit app score calibration, not official/measured monetary data; raw finding and #301 remain. |
| main `_budget_overview_meta` /1800 | `cache_ttl_seconds` argument to `_response_meta`, then section-unit metadata and returned `_meta`. Entire `get_budget_overview` function AST unchanged versus355c057. | Seconds metadata TTL; raw finding and #301 remain. |
| main `anchor_pct_gdp` /55.0 | Explicit code-declared legislative anchor in fiscal summary. Actual IMF ratio comes from DB; `above_anchor` remainsNULL and comparison reason says nominal/PV bases are incomparable. Entire `get_fiscal_summary` AST unchanged. This review does not independently re-certify the legislation. | Policy threshold/context, not actual debt ratio; raw finding and #301 remain. |
| provenance `budget_lines` /180 | `_STALE_AFTER_DAYS` -> `_apply_freshness`: age limit/status/response age metadata. `_apply_freshness` AST unchanged; no amount synthesis. | Source-age days threshold; raw finding and #301 remain. |
| provenance `gdp_data` /550 | Same exact lookup and stale comparison; annual table source-age budget, not GDP value. | Source-age days threshold; raw finding and #301 remain. |
| provenance `debt_timeline` /240 | Same exact lookup and stale comparison, not debt observation or ratio. | Source-age days threshold; raw finding and #301 remain. |
| cleanup `synthetic_budget_rows_unchanged` /2 | Check diagnostic accompanies full cleaned==expected snapshot equality. Disposable fixture inserts exactly2 explicit synthetic FK budget controls; no production amount is published. All module deltas reviewed: generator provenance/readback, actual post-code local recapture, new related/unrelated audit refusal/preservation controls. This counter/check and synthetic fixture remain unchanged. | Explicit local expected count; raw finding and #301 remain. |

Main module drift is from added truthful qualifications, source/county identity
readers and retirement of the unsupported inflation alias; provenance module
drift adds shared qualifications and removes round-number model guessing.
Neither extends these eight contextual sites to a measured-finance fallback.
The inventory now points to this review and355c057 prior context, retaining
whole-module drift detection. Other inventory entries are unchanged.

## Executed acceptance

- Red two all-tree guards: **6failed,843passed**,3warnings,65.82s.
- Green two all-tree guards plus whole-tree traversal and publication guard
  boundary controls: **1355passed**,3warnings,76.18s. This includes original
  invented county/national payloads, renamed keys, hidden numeric expressions,
  empty suppression reasons, sibling-site suppression isolation, inventory
  changed-use-context/refusal controls and parse/coverage anti-vacuity checks.
- Focused narrative/cache, financial-health disclosure, debt anchor, freshness
  and unit callers: **107passed**,3warnings. Cash-adoption37 tests skipped
  because they require explicit complete retained capture/catalog inputs;
  those were not sourced from private/production storage. No cash-operation
  runtime change is claimed from the annotations.
- Actual isolated PostgreSQL social queue: **64passed**,3warnings,6.91s.
  Loopback62081, unique disposable container, database`social_worker_test`,
  trust-only synthetic user, tmpfs data. Container removed after tests.
- `git diff --check` passed. No root/primary worktree, shared dependency,
  production/provider/credential or GitHub mutation occurred.

Logs are retained in the shared safe artifact directory as
`REMAINING_CI_SAFEGUARDS_RED.log`, `...GREEN.log`, `...CALLERS.log` and
`...SOCIAL_PG.log`. Counts overlap and are not summed. The original raw detector
still reports the eight contextual sites; a green inventory ratchet does not
certify universal financial sourcing or close unrelated tracked findings.
