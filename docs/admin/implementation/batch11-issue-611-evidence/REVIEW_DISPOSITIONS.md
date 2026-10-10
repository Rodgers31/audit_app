# Independent review dispositions

Review target: `dce199116052356851e99620553914ffa7b25efa`, tree
`161a96984077c0aaf95569c5baaa3a3a1b0fcd62`. Author, Spec, Standards and artifact
review were separate agents. Original reports/commands remain in the historical
bundle; later rechecks supplement them.

- **Valid:** linked-checkout recorder admitted common Git and sibling source
  destinations. Author reproduced the false passes in `author-hostile-red`.
  Shared output validation now excludes resolved common Git and every registered
  checkout. Both recorder and verifier use it.
- **Valid:** a testcase moved its output and replaced the path with a symlink;
  original recorder published a false PASS. Author reproduced it. Directory
  identity and resolved exclusions are rechecked after child execution and around
  each publication/readback; that control now refuses without publishing PASS.
- **Understated:** well-typed testcase/runtime/Git metadata substitutions passed
  the first verifier. Author reproduced all four categories. The repair binds
  retained producer metadata, actual runtime stdout, current Git/source/status,
  exact JUnit identities and primitive exits/counts. Normal and optimized
  replays use default bytecode settings, with no source cache writes.
- **Valid:** after that repair, an edited selected test file contradicted the
  actual JUnit inventory, and JUnit summary errors/tests contradicted cases.
  `author-shape-red-v2` reproduced both normal and optimized false passes.
  The parser now reconciles each suite total/outcome with actual cases; the
  verifier reconciles selected modules with executed classes in both directions.
  The first author shape attempt refused because its fixture status had changed;
  that setup attempt is preserved and is not the behavioral red.
- **Recorded limitation:** a party able to rewrite all retained records, outputs
  and hashes together can invent plausible platform/date origin. Local consistency
  checks cannot authenticate that party. README states this boundary; the final
  remote/source binder is separate and append-only. No universal artifact origin
  claim is made.
- **Standards heuristic:** possible Duplicated Code in database fixture cleanup.
  No hard standards breach. The browser has explicit lifecycle/readback while
  pytest has teardown after deliberate schema-damage cases; keeping the small
  independent protocols is reasonable here. A shared fixture helper is deferred
  until the production integration defines one lifecycle contract.
- **Spec:** bounded fresh-dataset proof matched its declared scope; production
  migration/router/model integration, history admission, restore/retention authority
  and natural lifetime wrap remain unmet. These requirements are carried forward,
  not reclassified as passes. The final browser/API journey passed with explicit
  zero-table/zero-role cleanup; independent Spec reviewed that fixture but did not
  execute the browser.

## Coordinator PR618 review, 2026-10-10

- **Valid / repaired:** table INSERT, column INSERT and inherited writer role
  allowed an unsafe reader. Effective table and column privilege checks now refuse
  each case with sanitized private/no-store503 before pagination.
- **Valid / repaired:** an altered issued snapshot could admit a late lower-ID
  commit. v3 authenticates the full snapshot, scope, UTC capture, ID ceiling and
  admin identity. Unchanged database controls refuse altered active/xmin/xmax,
  ceiling/as_of/scope, unsigned v2 and another actor. A process key change requires
  Refresh; authenticated concurrent replay and API filter transfer remain valid.
- **Valid / repaired:** source inventory followed an untracked symlink outside
  the repository. The additive `record_v2.py` / `verify_run_v2.py` pair rejects
  file/directory links and missing inventoried files; original producer and
  historical archive bytes remain unchanged. Explicit owned port choices, inert
  Git environment, bounded child lifecycle and external pytest temporary files
  preserve the evidence boundary.
- **Body-only / repaired:** browser output freshness was described but not
  enforced. Ordinary existing outputs and dangling destination symlinks now
  refuse before any report write; ancestor and checkout/common-Git guards remain.
- **Measured, bounded:** 92 cases pass on current and minimum SQLAlchemy/Python;
  the unchanged original implementation produced10 bookmark/privilege failures
  plus one source-link failure in the corrected pre-code replay. A first replay
  had collection/setup failures and is retained as NOT_ACCEPTED. Final source
  correspondence and browser execution belong in the separate external binder.
- **Remaining:** persistent/multiworker bookmark authority, legacy provenance,
  real migration/router/model activation, restore/retention and hosted admission
  remain #611/#583. These are not closed by prototype authentication.
- **Independent follow-up / repaired:** a successful pytest parent could leave
  a delayed descendant in its isolated process group. The v2 recorder now closes
  and reads back that exact group after normal and timeout exits, recording
  whether it survived the parent and each cleanup signal. Acceptance requires
  absent=true; the verifier requires the complete strictly typed lifecycle
  metadata. Real normal and SIGTERM-resistant child controls pass. Original
  false-PASS execution and any setup failures remain external diagnostics.
- **Browser lifecycle:** fresh output reservation records a random run nonce
  and directory identity for Playwright worker reloads. Existing/dangling output,
  linked ancestor, checkout/Git metadata and altered/fabricated worker markers
  refuse; a fresh coordinator and its inherited worker remain valid. This is
  local run identity, not authentication of an operator able to forge all files
  and process state.
- **Cross-lane evidence finding / repaired:** actual nonstrict pytest XPASS
  had a markerless passing JUnit testcase and was falsely accepted. The current
  recorder retains unexpected-pass status/summary lines from actual verbose
  stdout, including colored and interleaved output, and refuses acceptance.
  The reader independently recomputes those markers from retained stdout;
  recataloguing a false PASS with empty metadata still refuses under normal
  and optimized Python. An ordinary parameter named XPASS remains valid.
  Historical producers and archives remain unchanged; current final counts
  and source correspondence belong in the external publication binder.
- **Completion follow-up:** the first repaired recorder accepted a passing
  parent after closing its surviving group. Coordinator review tightened this
  bounded completion contract: unfinished child work cannot become acceptance
  through cleanup. Producer and reader now require survived_parent=false as
  well as absent=true. The actual pytest-parent regression was observed red
  against45236cc, then freshly rerun; that commit and its97-case receipts remain
  historical. Normal completion without survivors remains accepted.
- **Canonical discovery follow-up:** the owned epoch-one fixture was discovered
  by the ordinary e2e gate, which does not provision its dedicated API/database.
  Real canonical collection included it before repair. Current fixture/config
  move together to `frontend/browser-fixtures/admin-audit-epoch` with unchanged
  bytes/assertions; canonical config/workflow remain unchanged. Standalone
  execution and canonical exclusion are separately measured in the external
  binder. Historical source and browser execution paths remain historical.
- **Jest runner partition (#628):** hosted full CI later showed Jest's broad
  `*.spec.ts` match discovering the relocated Playwright fixture. Add only the
  explicit `browser-fixtures` directory to its existing test path ignores.
  All original unit/browser assertions, canonical Playwright config and
  workflows remain unchanged. Real Jest discovery before/after must remove
  exactly that foreign fixture; full Jest and the standalone owned browser
  journey are separately measured. The failed hosted run remains diagnostic.
