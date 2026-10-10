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
