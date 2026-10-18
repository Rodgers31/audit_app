# Retained Batch 15 laboratory observations

These are dated synthetic observations and independent review evidence for the
limited reset-loading height repair. Read root `HANDOFF.md` for commands, failed
attempts, the unqualified dependency graph, and original requirements remaining.
No record is a production/field/billing or full-lane acceptance verdict.

`baseline-bound.json` and `candidate-bound.json` retain their original bytes and
point to the original external measurement tool path. Its unchanged exact bytes
are preserved in `measurement-generator.cjs.txt`. Both captures inventory selected
tracked frontend/fixture source hashes and build IDs. They are observations only;
their layout-shift sums are not automatically session-window CLS. The original
external fixture adapter and raw setup attempts are retained in the shared packet.

Review probes and report producers are historical byte artifacts. Their `.txt`
suffix deliberately excludes them from executable/test discovery. Each review's
`ARCHIVAL_PATHS.json` maps original names to retained names with identical SHA256.
Original reports, receipt hashes and absolute paths describe the external review
run; they are not promises that archived probes are runnable from this directory.
Supported portable replay is the current
`frontend/browser-fixtures/reset-loading/README.md` workflow, which exercises the
actual installed frontend in Google Chrome. No old review receipt is relabeled as
fresh acceptance of later documentation.
