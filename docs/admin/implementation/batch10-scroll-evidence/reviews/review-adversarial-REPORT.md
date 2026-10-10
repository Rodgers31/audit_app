# Initial adversarial verification: changes required

Executed 70 isolated-copy attacks through `await verifyPackage(copy, repo)` on verifier SHA256 `5ceb1b64238a505ca53a586c4a7b7f1b2a9f32cb4b088df6277958467a05c126`; 14 malformed semantic inputs returned `archive_integrity: verified`. Real checkout sources and archived bytes remained unchanged. These are integrity binding defects, not causal scroll findings or proof of unauthenticated forgery resistance.

- **Required control role:** `negative-name-now-positive` replaces the native-absence target fields with the positive 20-case record while retaining the required negative name. It verifies without an executed negative detector.
- **Source/provenance binding:** wrong target receipt source hashes, commit/tree and log hash all verify; manifest wrong commit/tree and a source census reduced to eight unrelated files also verify. Required scroll sources and receipt identities must bind to the frozen archive, rather than arbitrary manifest claims.
- **Full-run receipt contradictions:** the full parent receipt can declare child/verification exit 1, timeout, source drift and changed generator yet verify. Wrong generator/source hashes and a cohort receipt containing an infrastructure error plus empty readback likewise verify.
- **Executed case identity/retries:** targeted report files, titles and lines can name nonexistent unrelated cases and verify. Full-run result `retry=100` verifies. The original 323 inventory can be consistently rewritten with a never-executed title/line and verify; its generator/commit are also unbound. Freeze the captured collection identity and validate targeted case identity and actual zero-retry accounting.
- **Compression schema:** an unused runtime entry with `compression: unknown` and input hash changed to the compressed-byte hash verifies. Reject unsupported encodings explicitly.

`attack.mjs` contains every exact mutation; `attack-results.json` records verdicts and before/after source hashes; `attack-stdout.log` preserves raw execution. Command: `node <this-directory>/attack.mjs` (exclusive result destination).

Additional direct calls reject null root/repo, missing and empty roots. Six actual publisher executions pass valid publication and reject an absent required report, inherited data/manifest, input mutation and publisher mutation during compression; partial data receives no manifest on mutation. The republished valid package verifies. See `publisher_attack.py`, `publisher-attack-results.json`, raw logs and `parameter_attack.mjs`.

Not executed: disk exhaustion, concurrent writers, adversarial ZIP decompression limits, browser replay, database or hosted jobs. #601 remains unresolved. This report is pre-fix; a fresh execution on amended source is required.
