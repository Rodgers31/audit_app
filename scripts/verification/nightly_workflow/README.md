Run the local semantic gate before handing off any workflow change:

```sh
python3 scripts/verification/nightly_workflow/semantic_gate.py \
  --root "$PWD" --actionlint /absolute/path/to/actionlint \
  --sha256 REVIEWED_BINARY_SHA256 --receipt /fresh/external/semantic.json
```

Use official actionlint 1.7.12, verifying the official release archive checksums
and retaining the extracted binary SHA256. The gate refuses missing binaries,
wrong versions/checksums, empty inventories and existing/source receipt targets.
Every `.yml` and `.yaml` workflow is checked. Shellcheck/pyflakes remain separate
checks. No workflow is enabled, dispatched or downloaded by this tool.

Execute its controls with that same supplied binary:

```sh
ACTIONLINT_BINARY=/absolute/path/to/actionlint ACTIONLINT_SHA256=REVIEWED_BINARY_SHA256 \
  python3 -m pytest scripts/verification/nightly_workflow/test_semantic_gate.py
```

This is offline schema/context validation, not a hosted GitHub compiler witness.
After a separately authorized push, inspect Actions run records for the exact
source SHA, run/attempt and nonempty job inventory, including zero-job failures;
an empty PR check rollup cannot certify workflow acceptance. Preserve complete
official job logs rather than relying on a combined CLI log excerpt.

Runtime integration is supplied by the runtime lane: use its immutable lock,
manifest and documented installer/qualification invocation after that delivery
is available. This lane does not select dependency versions or edit requirements.
