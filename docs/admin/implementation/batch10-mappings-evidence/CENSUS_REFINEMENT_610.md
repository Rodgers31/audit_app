# Final census refinement — 2026-10-10, #610

The initial repaired packet passed98 actual controls on each supported runtime.
Final review found its asset census exempted any file named manifest.json, so a
new unindexed nested manifest could be ignored. Two actual normal/-O rejection
controls then ran red against that verifier. The final version exempts only the
canonical root publication index and the explicitly unconsumed inherited
verdict. Any other unindexed file, including a nested manifest, refuses.

The first schema2 manifest/verifier/README bytes remain unchanged in
history/coordinator-610/schema2-initial-*. The original author packet, raw runs,
source ZIP and six ETL product files are unchanged. The V2 publication has its
own generator hash and names the intermediate publication as a superseded
validator. This does not supersede or relabel the historical executions.

Counted red/green commands, JUnit, exact source/generator hashes and final clean
commit identity remain external in MAPPINGS_REPAIR as described in
COORDINATOR_610.md. The final selection is100 packet controls per runtime,
including the20 unchanged behavioral guard selections and78 original repair
controls plus2 census refinements. Neither packet integrity nor these
evidence-only controls certify production or integration; root owns fresh
combined-candidate acceptance.
