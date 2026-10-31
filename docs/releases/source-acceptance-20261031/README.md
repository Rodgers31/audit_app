# Evidence index

Start with the [release record](../source-acceptance-20261031.md),
[validation receipt](validation-receipt.json), [source hashes](reviewed-source-sha256.json)
and [official input identities](official-inputs.json).

Root command receipts include the exact local Docker limits and test selection.
JUnit XML is gzip-compressed; failed RED/setup/resource attempts retain their
original results and are never counted as successful acceptance.

The portable replay helpers can run directly from any checkout; `.bytes` is
part of their committed filenames, not an instruction to rename them:

```sh
python3 docs/releases/source-acceptance-20261031/run-final-selection.py.bytes normal
python3 docs/releases/source-acceptance-20261031/run-final-selection.py.bytes optimized
```

They locate the checkout from the script's ancestors. Set
`SOURCE802_SOURCE_ROOT` to override that source directory and
`SOURCE802_EVIDENCE_ROOT` for a prepared writable input/output directory.
Otherwise each invocation creates a fresh temporary evidence directory and
prints its location. Existing receipt names are refused; the selection helper
uses a unique name. The cached runtime image and guarded, owned `source802-pg`
and compatibility PostgreSQL fixtures remain prerequisites. No fixtures are
provisioned and no production database is selected by these helpers. Genuine
input replays additionally require the exact separately retained inputs and
test scripts in the prepared evidence directory.

`original-replay-helpers.tar.gz` retains the original author's two helper bodies
for historical evidence. Recorded command receipts and sealed review packets
remain unchanged; the current helpers are the portable replay entry points.

The independent Standards report, case ledger and source bridges are readable
under `standards/`. Its `packet.tar.gz` contains all sanitized top-level sealed
artifacts (no full official PDFs/HTML, snapshots or credential env files). Extract
that archive into a new directory and run `python3 verify_packet.py` there to
check its hashes and ledger. That verifies receipts without claiming a test rerun.
Actual source replay also needs the separately retained exact genuine input
bodies, the cached runtime image and guarded owned PostgreSQL fixture documented
by the commands. Neither archive extraction nor integrity checking downloads or
installs anything.

The [Spec report](spec/REPORT.md) and receipt are under `spec/`. Its archive
preserves the `candidate3` execution records and `candidate4` final-source/test-only
carry records, without the full source snapshots or official PDF bodies. Its
case ledger distinguishes actual execution from inspected author PostgreSQL
tests; the latter are credited only in the root and Standards receipts.

Full local packets retain unsuccessful setup attempts, source projections,
input bodies and detailed process/resource traces. Local test acquisition and
job clocks cannot establish a new official publication date or production
adoption. Backend tests do not certify the production UI.
