# PR860 fiscal review repair — scoped acceptance

No remaining finding in the two reviewed fiscal comment repairs. The original findings and desired failing controls remain preserved in `../REPORT.md` and `../FINDINGS-RECEIPT.json`.

| Execution | Distinct cases | Passed | Failed | Errors | Skipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original 16538db, normal | 11 | 7 | 4 desired RED | 0 | 0 |
| Original 16538db, true Python `-O` | 11 | 7 | 4 desired RED | 0 | 0 |
| Repaired snapshot, normal | 15 | 15 | 0 | 0 | 0 |
| Repaired snapshot, true Python `-O` | 15 | 15 | 0 | 0 | 0 |

The final runs execute the unchanged original 11 controls plus four material helper edges. That is 15 distinct final cases, executed twice. Both final child exits are integer zero; every JUnit testcase is unique and passing.

The inline per-year coverage finding is closed: absent current-source coverage leaves the revenue component/domain below `live`, even when old values and source URLs already match. The added accumulator controls establish that refused revenue-basis assignments and old source tags earn no fresh-year credit; a newly assigned own-year Annex revenue does.

The body-only competing-edition finding is closed for conflicting approved editions of the same fiscal year. Both source orders refuse before financial promotion, including use of those editions for historical rows. Identical editions remain accepted. Distinct edition-year vintages still join through the row's exact revenue-source document; newer actual and older approved figures both retain their correct source. Wrong-document borrowing and broken arithmetic remain refused.

Source identity: immutable repaired projection contains 1,559 backend/tools/.github files, canonical mapping SHA256 `043687b455b5c0aee72ee64a79f72c295a812f01ae66a88abd544da121eda0a9`, based on `16538db009704ece4e0aaa51ac162752d591180c` plus the captured repair. Every source file was rehashed after execution with no changes. Current checkout fiscal fetcher and fiscal-framework files exactly match the reviewed bytes:

- `fetcher.py`: `5851e98aaab5264bd08164537c2084c8f5e63d75919c44092762e376ccd4b868`
- `fiscal_framework.py`: `a37dd8759593fc906d2e317fcc32dc1a9494b082b32834408961773a61d5cb60`

Exact commands, stdout, integer child exits and XML are in `../repaired-normal/` and `../repaired-optimized/`. The case inventory is `../repaired-case-ledger.json`; source pins/readback and all evidence hashes are bound by `FINAL-RECEIPT.json`.

Execution used only cached image `admin-redesign-python-runtime:local` (`sha256:571e327e2fbe507713d267f6f15050d585a5bbb53b8ec2e3afc73db2996d6d2d`), `--network none --cpus 1 --memory 1g --pids-limit 256 --rm`, source mounted read-only, and all four social safety flags false. No product/test checkout edits, PG/shared containers, production, providers, network acquisition, hosted actions or installs. No persistent review resources or real credentials were created.

Limits: acquisition callbacks supplied coherent typed fixture outputs. Actual revenue-series construction, financial parsing/reconciliation, apply helpers and final component/domain verdicts executed. This does not certify new live source contents, OCR repair behavior, debt changes, deployment or production readiness. The original evidence-only collection SyntaxError is retained and uncredited; it predates the stated successful baseline execution.
