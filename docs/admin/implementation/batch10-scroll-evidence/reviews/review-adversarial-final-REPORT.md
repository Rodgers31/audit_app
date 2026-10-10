# Second adversarial verification: additional changes required

Verifier SHA256 `be70e7be74d0fd5cca4c1ff4af3d00af458f78e89149a0a4cfaa827cb03dd67e` rejects every prior false success: exact unchanged 70-case harness rerun, zero unexpected outcomes. A further 22 direct isolated-copy executions found 18 remaining malformed semantic acceptances. Sources stayed unchanged during each execution; the author updated only a unit fixture between runs, recorded in both receipts.

- **Commands:** absent, empty, null or unrelated target commands verify. Inventory/cohort commands can be unrelated. Full parent command can become `echo <runner> --no-browser` while retaining the runner path source hash and verify.
- **Consumed probe/generator inputs:** archived probe spec, both hook versions and configuration can become unrelated code after updating file hashes, despite unchanged consumed-input hashes in receipts. An unrelated `run_record_v2.py` plus changed generator hashes likewise verifies while receipt consumed-source identities still describe the original generator.
- **Publication completeness:** deleting launch, Python and both runtime records, and deleting their manifest entries, verifies. Those are required publisher inputs for this frozen lossless publication.
- **Observed diagnostics:** negative error location/stack can identify unrelated code; positive probe measurement attachments can be absent. Existing fixme annotations can become runtime-prerequisite skips. Positive and negative `spec.ok` fields can contradict individual result verdicts. Each verifies.

These findings concern contradictory/omitted facts in a known frozen historical package. A pinned raw-input path/hash census would bound this package without suggesting protection against an attacker rewriting both code and evidence. No cryptographic authentication or causal repair is claimed.

Exact executable cases are in `extended_attack.mjs`; `extended-results.json` and `extended-stdout.log` preserve outcomes and source/harness hashes. Prior harness, current results and logs are `attack.mjs`, `attack-results.json`, `attack-stdout.log`; initial review remains untouched.

Six fresh publisher controls behave correctly: valid publication; rejection of absent required input, inherited outputs, input mutation and publisher mutation. Mutation leaves partial data without a published manifest. See `publisher_attack.py`, `publisher-attack-results.json`, `publisher-attack-stdout.log`.

Not executed: concurrent writers, disk exhaustion, decompression resource bounds, browser/database/hosted behavior. #601 remains unresolved. Further amendments require another fresh execution before an all-clear.
