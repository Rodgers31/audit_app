# Batch 8 shared exclusion implementation contract

Pinned source: 97fe77462b4e63ffad7dc393b8bf97d3e51571f7. Scope: #572.

Add one model to `backend/models.py` and one additive migration. No existing
financial model, parser, writer, registry, API or frontend contract changes.
The other Batch 8 lanes do not own models or migrations. This narrow expansion
is required because the current dispatch-domain table accepts only audits and
requires a dispatch command FK; it cannot represent standalone native ownership
for every domain selected by the existing CLI's --all interface.

`seeding_domain_claims` retains ownership history. A partial unique index permits
one unreleased claim per domain. Native acquisition and worker claim insert
against that same index in a transaction, before any RUNNING observation or
handler invocation. Dispatch retains its existing command-domain correlation;
its shared claim uses the server-created claim token.

Entry is durable and one-use (`entered_at`, `entry_id`). A native claim is
entered as it is acquired. A dispatch claim is entered only when the CLI, before
any handler, re-proves against durable rows the exact claim (kind `dispatch`,
domain, command), the running command with `execution_started`, its claim token
and generation, the dry-run intent, the dispatch-domain row and a fresh worker
lease of that same generation, and then records the entry in that transaction. The adapter supplies
these identifiers through a process-local scope; namespace, environment and
arbitrary caller metadata cannot supply it, and a scope that names no matching
unentered claim starts no work and only records a FAILED `ownership_refused`
observation. Acknowledgement requires the entry nonce the entering object
received, together with the matching claim id, domain, kind and command, so an
object that never entered — or names another domain's claim — cannot acknowledge
or release anything. The claim stores only a one-way digest of the nonce, so a
database reader cannot acknowledge either; only a database writer could, by
changing rows directly.

The executing runner holds a transaction-scoped advisory lock inside a
transaction kept open on a dedicated connection until it finishes (this pins one
backend behind a transaction pooler, and the lock cannot outlive it on a pooled
connection; it disables the idle-in-transaction timeout for that transaction and
checks continuity immediately after locking), and verifies that same backend and
lock still exist before acknowledging synchronous runner
return and a coherent terminal observation. Connection/lease loss, SIGKILL or
SIGTERM/SIGINT before acknowledgement, or absent/malformed receipts retain
ownership. A child exit does not acknowledge runner return. A per-domain or
global-budget timeout is raised by SIGALRM in the runner's own thread; once the
CLI has regained control, rolled back and recorded the FAILED observation, it is
a synchronous runner return and is acknowledged like any other handler failure
(the pre-existing timeout semantics — exit status, FAILED receipt, global stop —
are unchanged). Native normal terminal acknowledgement releases its claim;
dispatch acknowledgement remains held until the fresh supervisor commits the
fenced command receipt. A dispatch claim the CLI never entered is released by
that supervisor's `finish()` with a `failed` command and no job: entry re-proves
the running command and unreleased claim under the same row locks, so nothing
can enter afterwards and no handler can have run. No expiry-based reclaim,
deletion or unblock tool. A RUNNING observation without a seeding claim tag
(a writer outside this seam, e.g. from before the migration) refuses its domain
with no age limit; tagged observations are governed by their claim. The
migration records copied Batch 7 claims whose command had started as entered,
so they can be neither acknowledged nor treated as never entered.

Quiescence of uncertain writers requires stopping ALL native/scheduled/dispatch
entry points and process groups, proving their database and external writer
sessions/work are stopped, then reconciling each claim's exact effects and
observations. Explicit release remains a separately reviewed operational action;
the schema records it honestly as `released_at` with `reconciled_by` and
`reconciliation` (no runtime path writes these), never as a fabricated return.
Writers outside `seeding.cli.run_seed_command` are not covered by this seam; the
inventory and the quiescence they require are in
`BATCH_8_NATIVE_EXCLUSION_HANDOFF.md`.
No implementation or test here authorizes production migration or activation.
