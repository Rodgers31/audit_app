# Recovery operator qualification limits

The recovery operator is default-refusing. Argument parsing, execution and engine
cleanup share one private diagnostic boundary. A cleanup failure invalidates a
successful operation before its result is printed. `--help` remains available.

Actual snapshot export requires Linux with `/proc`, kernel child-subreaper
support, `pidfd_open` and `pidfd_send_signal`. A fresh isolated Python guardian
starts the explicitly selected local `pg_dump`. It owns adopted descendants,
including children that detach into another session; it never changes the API
process's subreaper state. It signals only kernel-identified direct children
through stable pidfds, reaps them, and refuses an exited exporter with surviving
descendants. Deadline, interruption, nonzero exit or uncertain cleanup cannot
produce an accepted dump. Non-Linux/unsupported hosts refuse before launching
the exporter. Process-group disappearance alone is insufficient evidence.

Database inventory currently supports selected-schema ordinary/partitioned
tables, views, functions, sequences and enums. Standalone composites, domains,
ranges and custom base types are refused rather than compared by type name.
Recursive column type dependencies outside the selected schema (except built-in
`pg_catalog` types) are also refused. This includes external enum/domain arrays
and composite members. These refusals are not complete-cluster recovery support.

Privacy reconciliation must match the entire signed intent to the exact current
execution, plan, policy and frozen scope before any erasure. A valid signature
for a different policy cannot bypass a previous exact-intent persistence
refusal. Restore suppression remains a separately authenticated operator path;
neither path authorizes full deletion, key retirement or publishing.

Local source-removal drills prove only the executed owned database/runtime.
Off-host custody, production role/schema integration, externally retained backup
copies and actual provider/storage acceptance remain separate gates. All new
features, publishing, media uploads and worker activation remain off.
