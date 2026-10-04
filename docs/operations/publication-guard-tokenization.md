# Publication guard suppression tokenization

The backend runtime investigation at `71d44f45e0ecd0ace05b13f37d2518df5e37c1a9`
found repeated tokenization of unchanged complete source text for each
suppression site. Under identical coverage and cProfile settings, the 546-case
financial/context/publication cohort passed in 58.18 seconds before this
optimization and 35.23 seconds after. The main-module financial guard call
fell from 21.25 to 1.18 seconds. These are local Python 3.13.9 measurements,
not a guarantee of hosted whole-suite runtime.

The shared suppression helper now caches only reasoned comment positions for
the exact reconstructed source text and marker string. The eight-entry cache
returns a frozenset of immutable line/column tuples. Source changes, reason
changes and marker changes produce distinct keys. AST nodes, owner decisions,
suppression booleans and scan verdicts are not cached. The existing inline and
standalone comment ownership rules run against the current AST sites on every
call. Marker matching and reason grammar are unchanged.

The same 1046 suppression calls consumed 22.201 seconds before and 0.470 after.
Tokenizer yields fell from 25,554,372 to 391,434. Reading 1661 source files
consumed only 0.149 seconds in the baseline; file reading was not changed.
The separately measured covered owned PostgreSQL backup/logical cohort passed
59 tests in 17.72 seconds and provided no reason to alter its lifecycle gates.

Regression evidence:

- A repeated-source control failed the original helper with six tokenizations
  and passed the optimized helper with one, preserving every site decision.
- Seven focused cache controls passed, covering reason/source/marker changes,
  current AST ownership, immutable results and bounded eviction.
- Original versus optimized outputs were exactly equal for all 444 current
  source modules in each of the financial figure, zero fallback and endpoint
  advertisement detectors.
- An independent reviewer executed 504 controls and found no supported-input
  semantic difference or stale approval. Malformed list/dict marker arguments
  now raise TypeError where comment-free input previously returned False;
  neither behavior approves suppression. The declared marker contract is str.

Reviewed inventory bytes, per-site dispositions, source scanning scope,
financial thresholds and context fingerprints are unchanged. The runtime
fixture optimization owned by the other workstream is separate. Hosted frozen
whole-suite verification remains the final runtime acceptance gate.
