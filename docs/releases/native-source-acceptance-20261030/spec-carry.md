# Candidate 3 audit dependency carry

**Audit-only acceptance carries from candidate 2 to candidate 3.** No project code was re-executed and no PG was created for this carry check.

Candidate 3: 6,037 files, mapping SHA256 `dbbe7eb21d4b35c90165ee11ca7ae1749cc71e4e48c95bee67368f46aeebd82a`. Every on-disk file hash and the exact file set match the immutable manifest. The only changes from candidate 2 are `backend/seeding/domains/revenue_by_source/press_evidence.py` and `backend/tests/social/test_kra_press_source_acceptance.py`.

All 11 audited product/test dependencies are byte-identical to the tested candidate-2 dependencies. Therefore the existing 87 normal and 87 optimized audit cases (zero final failures/errors/skips) retain their stated scope. Original XML, commands, case ledger and input identity remain in `../final2`; this carry does not relabel them as executions on candidate 3.

KRA candidate-3 behavior/acceptance remains the separate Standards review. This artifact supplies no overall #802, production, worker, publishing or source-acquisition acceptance. No repository edits, product execution, provider/network action or credentials were needed for this read-only host-stdlib hash verification. The earlier owned PG fixture and credentials remain cleaned up.
