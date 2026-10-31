# Evidence index

Start with the [release record](../source-acceptance-20261031.md),
[validation receipt](validation-receipt.json), [source hashes](reviewed-source-sha256.json)
and [official input identities](official-inputs.json).

Root command receipts include the exact local Docker limits and test selection.
JUnit XML is gzip-compressed; failed RED/setup/resource attempts retain their
original results and are never counted as successful acceptance.

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
