# PR862 review disposition

The [inline portability finding](https://github.com/Rodgers31/audit_app/pull/862#discussion_r4431152440)
is valid and understated: the root helper mounted the author's absolute checkout,
and its companion also requested filenames absent from the committed bundle.
Root reproduced both failures in a relocated checkout with an intercepted Docker
executable before the repair. The helper now resolves its enclosing checkout or
an explicit `SOURCE802_SOURCE_ROOT`, and the companion uses the actual committed
helper and `selection.txt`. Both `.bytes` files run directly with Python.

The same review exposed implicit normal mode for unknown values and overwriting
historical receipts. Modes and receipt basenames are explicit; fresh output is
the default, repeated names refuse, and the companion uses unique replay names.
Independent review then found blank root overrides selecting the current working
directory and dangling receipt symlinks escaping the occupied-output check.
Root observed both RED, then fixed the shared root/output guards. No application,
financial source, schema, worker or operational configuration changed.

The [22-case permanent CLI regression](test_portable_replay.py) passes normally
and under actual Python `-O`; it intercepts Docker and starts no container.
It covers relocated/default/explicit paths, spaces, malformed/missing roots,
companion inputs, fresh names, existing/dangling outputs, invalid mode/name and
failed-child status/receipt preservation. Independent Spec executes six separate
controls per mode; Standards executes all22 and separately verifies the local
merge coordinator. Coordinator tests are tooling evidence, not application test
credit or permission for an owner override.

The original helper bodies remain in `../original-replay-helpers.tar.gz`.
Recorded `.command.json` receipts, the original RED/GREEN source evidence and
sealed source-acceptance review packets are unchanged. Historical558 cases per
mode and genuine-source/resource acceptance carry through byte-identical backend
source; this documentation/tooling change is not mislabeled as a new558-case run.

The first root portability replay after repair had a harness path-alias mismatch
(`/var` versus resolved `/private/var` on macOS); it receives no GREEN credit.
After correcting only that harness expectation, the original portable paths
pass. Root and independent normal/optimized receipts remain distinct.

Publishing, uploads, workers and financial generation stay off. No paid review,
hosted rerun, service, plan or allocation was added. Deployment and production
readback are separate release steps; #802 remains open for its explicit source
and operator gates.
