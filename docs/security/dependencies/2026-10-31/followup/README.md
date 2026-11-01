# Follow-up evidence

The [follow-up report](../../../DEPENDENCY_FOLLOWUP_2026_10_31.md) interprets
these results. The full raw npm audit still exits 1 with 22 package entries;
production exits 0 with no findings. No advisory is suppressed or relabelled.

* [Final author acceptance](author-acceptance.json) binds all seven executable
  inputs to the completed post-review runs. Earlier pre-guard/diagnostic runs
  remain in the external evidence directory and are not final acceptance.
* [Independent Spec report](spec/REPORT.md), [binding](spec/source-binding.json),
  [version matrix](spec/runs/version-matrix.json) and [replay instructions](spec/REPLAY.md)
  cover the specific minimatch mechanism, real legacy callers, corrected
  modern regression and independent deepmerge/installer controls.
* [Independent Standards report](standards/REPORT.md) and
  [final binding](standards/FINAL_BINDING.json) cover official package identity,
  all shipped deepmerge code entries, hostile object inputs and the resolved
  repair-exclusion guard. Each review directory has a publication hash inventory.
* The author separately replayed the [upstream amplification trigger](minimatch-author-replay.json)
  and [legacy backtracking control](legacy-backtracking-author-replay.json).

Review bindings identify the staged candidate above parent commit `45bb6b9`;
their executable hashes, rather than that parent HEAD alone, identify what ran.
The publication step checks those bytes again. Reports, receipts and harnesses
are copied from owned evidence. Vulnerable historical fixture manifests are
archived with `.json.txt` names so they are not active dependency manifests.
Downloaded package trees, registry caches, original tarballs and diagnostic
development history remain outside the repository.
