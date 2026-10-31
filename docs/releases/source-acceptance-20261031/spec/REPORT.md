# Final OAG source-contract Spec review — scoped pass

**95/95 cases pass normally and 95/95 pass under true Python -O**, zero failures/errors/skips. No remaining finding in the reviewed OAG RSS/cover/stored-contract scope. The original punctuation-conflict REDs remain preserved and pass unchanged after repair. This does not close #802 or qualify every production OAG source.

## Final byte binding

Final backend/test projection: **1,476 files**, `source`, mapping SHA256 **e005c70b78d5870a3f39f2873ea7987fd7037467a83e8df9925e1487ecc37e64**. All final files rehashed and matched the current checkout after execution.

The tests executed on runtime projection3, mapping **de915683c25278cbd3d36cefed09b2ee909856c16ffa05ae3dad2541c6e78085**. Final projection4 has **identical product bytes** and exactly two inspected test-only deltas: the seventh PostgreSQL baseline/change/concurrent-replay case with its transport fixture extension, and an additional catalogue human-review assertion. Both diffs are retained; no repeated expensive runtime test was needed for these unused test bodies. This report does not falsely claim all executions mounted final projection4.

Key final product hashes:

- `native_report_cover.py`: **e45eeb82288293d991138c811756a93cfffc7d5474a9033fa8197976ba1addff**
- `native_report_authority.py`: **5e9a94bf42eda9a3321edf0ff5982bad2548d4e6b7c28c6b3c027839b0cff230**
- `oag_report_catalogue.py`: **6b22f1c46a1cde4f7406fbda8595bb64e742c0dffbce592b6d1bf9cbab4b9635**
- `social_copy.py`: **b13dd58453542214d66c6ba434e263a30b816b64e3a93c44fe3aae3bd4ccd8ed**

## Executed coverage

| Scope | Cases per mode | Result |
|---|---:|---|
| Original independent RSS/cover and genuine/current-consumer controls, plus four FY22 pair/mismatch cases | 34 | All pass at **512 MiB**, 53.60s normal / 53.30s optimized |
| Unchanged stored metadata/receipt/scalar/date/pair/job validation controls | 48 | All pass |
| New cover reader lifecycle, glyph parity and fourth-page controls | 13 | All pass |

There are **95 defined tests, 190 executions**. Supplementary genuine text-parity/memory processes are separate receipts, not extra pytest cases.

The four actual retained executive/assembly PDF+RSS pairs for FY2022/23 and FY2023/24 qualify only catalogue availability. Both actual FY2024/25 volumes remain refused, including with their real empty feed. FY22 PDFs paired with the foreign FY23 feed refuse. The actual accepted FY22 values validate as the exact OagCataloguedReportEvidence type; captions name FY2022/23, say **an audit report**, retain unknown report publication date and human review, never claim latest, and source_scope actually refuses with CATALOGUE_HUMAN_REVIEW_REQUIRED. Current KRA model/copy/policy controls remain green.

All accepted OAG pairs retain **published_on=None**. Full RSS timestamps attest catalogue entries, not signed PDF publication or first availability. The original strict source/body/receipt, scope, chronology and ambiguity controls remain active. The two candidate1 separator-conflict fixtures now refuse without test changes; complete conflicting title pages, canonical kind/year conflicts and explicit PDF publication labels continue to refuse.

The 48 stored controls exercise actual minting plus validators shared by current-reader/persist paths, with structural, scalar, seal, scope, timestamp, pairing and job-boundary attacks. The stored retained-current-pair positive manipulates stored dictionaries to test chronology; it is not a PostgreSQL retained-origin proof. Actual runtime seal tests and genuine captures are separate.

## Cover reader proof

Eight instrumented lifecycle cases test page/stream cleanup across normal, early and failure paths. Four actual owned-PDF comparisons cover text, vector, image and Form glyph output. An actual four-page reader trap proves the helper does not advance to page4. Mock lifecycle instrumentation is kept distinct from actual glyph tests.

A separate genuine FY2023/24 executive PDF comparison (SHA256 **bf36d9e65b7403f9ce66eaf32890834f546ca3674c331a2d5f734f9e68c59bcd**, 34,055,119 bytes) produced **identical first-three numbered page texts** with standard pdfplumber and the new helper: lengths 551/241/102 and identical per-page hashes. Standard ran successfully at 1 GiB; the helper ran successfully at 512 MiB with recorded cgroup peak **162,336,768 bytes** and 8.49s. This is one measured corpus file, not a universal memory/performance guarantee. The full reader selection also ran both modes at 512 MiB over the six genuine PDF bodies.

## Receipts and boundaries

`CASE-LEDGER.json` points to each real JUnit node. Exact commands, exits, logs and observations are under `../candidate3/reader-review/` and `../candidate3/cover-review/`. The latter includes the separate GENUINE-PARITY.json, memory/text hashes and lifecycle report. Source/test-only carry is documented in `input-pins.json`, `SOURCE-AFTER.json`, the two manifests and the inspected diffs. `INPUT-ARTIFACTS.json` pins every supplied PDF/feed/category body used. `REVIEWED-ADR0003.md` records the explicit narrow catalogue policy. Candidate1 and baseline RED evidence was revalidated unchanged.

The first carry guard deliberately refused when a second test-only change was found; both test diffs were then inspected before final capture (`CARRY-GUARD-ATTEMPT.json`). No project test failed during final verification. All project execution used cached, owned network-none Docker, 1 CPU, 256 PIDs, at most 1 GiB (genuine reader/helper proof at 512 MiB), frozen source/tests and retained inputs read-only. No source edits, PG, project env/credentials, provider/production access, flags, publishing/uploads/workers, dispatch or paid services were changed or activated. No owned resources remain (`CLEANUP.json`).

Root's seven PostgreSQL producer/preview/replay/concurrency/restricted-worker tests were **inspected as a test-only delta, not executed or counted by this independent review**. This report does not substitute for their actual DB/witness receipts, an operator deployment check, universal malformed-PDF safety, all-nine qualification, or production acceptance. Latest missing metadata remains unavailable; #802 stays open for unsupported sources/upstream/operator gates.
