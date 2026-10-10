# Independent acceptance of bounded tooling repairs, including distribution

All 551 unique controls passed on Node 22.19.0 / Darwin arm64. Counts: 162 original controls replayed against the ten-file patch set; 118 expanded installer, inventory and AST controls; 271 independent source/distribution formatting and regeneration controls. Fail/error/skip/xfail counts are zero. Every execution producer and the separate result assessor exited 0. Actual raw child exits and diagnostics are retained. All owned fixture paths were absent after cleanup, and all seven source hashes matched across the three producers and their final readback.

No remaining reproducible invariant defect was found within the bounded repair scope. The original four findings are fixed, and the previously outstanding distributed-entry precision failure is fixed as well. Earlier candidate and pre-distribution reports remain unchanged in their original artifact directories; this run has a new source and generator identity.

## Actual measured behavior

The source and minified distribution entries both reject excessive e/f/g precision with ERR_SPRINTF_PRECISION through sprintf, vsprintf and direct format. NaN, infinities, negative, boolean, null, empty and malformed direct precision inputs reject before argument callbacks. Valid public boundary formatting, named/positional/string/literal formatting, and callback/getter precision/conversion snapshots remain exact at both entries.

The actual locked Next bundled Terser was independently executed on the repaired source. Its generated minified bytes exactly matched installed SHA256 7b3f54d49ea44e746cbf4843486318e77006f5ecd6a7d3bdce6f0c6bad1a1cd4. Both actual source maps matched generated SHA256 aaf7c7e9570f04faa734caac120c6b4ea9b06431c8613647defc9ffc3c9be57d and embedded the exact repaired source SHA256 52e8843b7e4ea7daa61582942dea76af3fd9961bfc7f0be0af387803d6a9ca7f. The executed minifier SHA256 was e4ae9a64825ea7f53606c3ee01633f08b64e12000a30d3687f52b64977f9a652. This verifies generation correspondence through real code execution, alongside actual library behavior.

Cold owned fixtures reverse-reconstructed every one of the ten upstream patch targets and verified their original hashes before executing the actual installer. Precheck failed, all ten repairs applied, repeated application was idempotent, and final check passed. Every patched target was independently changed/deleted and rejected. All 27 complete package inventory files were separately changed/deleted/symlinked and rejected. Extra files, entrypoint metadata drift, genuine omission versus parent/package symlinks, temporary-file collisions and real concurrent installer processes were replayed. Existing unrelated collision bytes survived actual wx failures; created temporaries and owner locks cleaned up after injected publication failure. Deep/cyclic direct AST append inputs raised the policy depth error before stack exhaustion.

## Source identity and replay

The measured checkout was launch HEAD bcb5ff99854de595bbe3f7d60cc8796b7ada5a20 / tree 9d0061928c16d173859f98cb6daa5f2f591b257c with the recorded uncommitted author delta. Installer SHA256 is acd61ee77794572624afa1cfdb030ca80bf482148a3b4a213681e1bc453956fa. Manifest SHA256 is e592d387fab60573cd11f5565f838b06f5d3551fa136a433fa7db1262ac4c8a5. Expanded-replay/source/ preserves the tested seven source files. All runtime, caller-resolution, source and generator identities are in the three identity.json files; acceptance-assessment.json holds the complete nonempty unique control inventory and counts.

Portable producer invocations, each with a fresh owned output directory:

```text
node original-distribution-runner.cjs CHECKOUT_ROOT FRESH_ORIGINAL_OUTPUT
node expanded-distribution-runner.cjs CHECKOUT_ROOT FRESH_EXPANDED_OUTPUT
node distribution-behavior-runner.cjs CHECKOUT_ROOT FRESH_DISTRIBUTION_OUTPUT
```

The original and expanded producers are separately retained derivatives of the earlier producers; their identities are measured rather than reassigned to historical runs. The distinct distribution producer resolves sprintf through the real declared chain @istanbuljs/load-nyc-config -> js-yaml -> argparse, then executes the real src/dist entries. Children receive only allowlisted PATH and inert HOME. Child deadlines are 10 seconds and concurrency scheduler deadlines are 5 seconds. The production/source checkout and its installed libraries were read-only; all mutations occurred in exact owned fixture copies. No primary-checkout operations occurred.

This report supplies local adversarial acceptance of the measured bounded code. It does not change advisory metadata or upstream package versions, infer universal caller trust, or grant a residual-risk exception. It does not supply Linux/native/model/browser/build/audit/hosted/production acceptance. Those remain separate author/coordinator verification obligations. Later source or published-corpus changes need a new measured recheck.
