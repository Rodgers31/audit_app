# Independent reviews (#602 continuation)

Two reviewer agents ran in parallel, each separate from the author and from the
other: one on **Standards**, one on **Spec**. Each worked in its own worktree,
on its own owned PostgreSQL and API ports (55541/18041 and 55542/18042), and
executed its own controls. The harness blocked them from writing report files,
so their reports are reproduced in the author's handoff and PR. Their command
logs and probes are external:

- Standards: `/Users/roger/.codex/visualizations/2026/10/10/01a12626-69b6-7d82-9083-54e4bf07a86b/issue602/claude-continuation/review-standards/` (`control-NN-*`, `r2-control-*`, `probes/`)
- Spec: `.../claude-continuation/review-spec/` (`runs/`, `probes/`, `live-get/`, `recheck-*`)

## Round 1 — reviewed commit a1bfd636 (tree 2ff59160)

Both reviewers: the batch11 suite passed 149/149 and the preparer suite 15/15,
on both runtimes. The Spec reviewer independently hashed both the public CRA
URL and the committed fixture (`38189f66…498a`) and re-extracted page 39.

| Finding | Axis | Disposition | Proof |
|---|---|---|---|
| Writer accepts any backend holding the CRA key (contender after the runner's lock died) | Standards (reproduced) | valid, fixed: holder's `xact_start <= claim.entered_at` | `receipts/red-06-*` red, then final cohorts green |
| Replay keyed on stored `parser_sha256`: a tampered row with another hash survives and a second row is appended; a parser edit appends | Spec (reproduced) + Standards | valid, fixed: any other extraction on the CRA document refuses | `receipts/red-05-*` red, then green |
| Uniformly ×10 table passes layout and arithmetic | Spec (observation) | hardened: table value cells must appear in the separately extracted page text | `red-05-*` (scaled case) red, then green |
| Claim `FOR UPDATE` held across the network fetch | Standards | fixed: pre-fetch check `lock=False`; `persist` re-proves with the row lock | code |
| `record_publisher_edition` called with a hard-coded, unobserved edition | Standards | fixed: removed | code |
| Generic `mark_refused` with no detail; magic `4`; mixed FY spellings | Standards | fixed | code |
| `validate_page(61.0)` accepted; title checks are substrings; PDF reader errors are not `CraSourceRefused` | Standards | fixed, with tests | `test_title_page_count_and_reader_errors_refuse` |
| An invalid flag is logged as an import failure | Standards | fixed: `dispatch_cra_flag_invalid` | `receipts/red-07-*` red, then green |
| Decimal-rounding test refuses on shape; `pytest.raises(Exception)` | Standards | annotated / tightened; the numeric bound is pinned by the real-layout oversize test | code |
| OpenData gap text cites #602 | Spec | fixed: #621 | code |
| A malformed flag stops every seeding run | Spec + Standards | recorded decision: fail closed rather than guess the operator's intent | handoff |
| Flag-off CLI says `Unknown domain(s) requested: cra` | Spec | recorded decision: the domain is not registered while off (clean-process loader test); dispatch gives the reason | handoff |
| Batch10 test edits outside the named hunk, not journaled | Spec | journaled as consequential hunks (pending coordinator) | requests journal |
| Duplicated lock-key formula; flag read in two places | Standards | kept as judgement calls (the formula is asserted equal by a test; `exclusion.py` is #603's) | reviewers accepted |
| Handoff, minimum cohort, full run and item-6 receipts missing | Spec | delivered in this packet and the handoff | `receipts/final-*`, `probes/` |

## Round 2 — recheck at 5d62b1d (tree 53c782b1)

Both reviewers re-executed their probes on both runtimes; batch11 passed 159/159
and the preparer 15/15. Every round-1 code finding is reported fixed. Both
reviewers named the same residual, which the Standards reviewer reproduced
(probe P1b): a transaction begun before the claim's entry that takes the key
after the runner's lock backend dies still passes the `xact_start` binding. It
is not reachable through the shipped `DomainExecution.open()`. Acknowledgement
still re-proves the runner's own pid, so such effects land under a retained,
uncertain claim, not as a takeover. Closing it fully needs a handler-visible
execution identity in `seeding/exclusion.py` (#603), requested in the
coordination journal.

Not executed by the reviewers: batch9/batch10 cohorts and the full suite (the
author ran those, see `receipts/final-*`), lint, and anything hosted or in
production.
