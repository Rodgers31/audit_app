Evidence for the [release record](../overview-source-health-20261031.md).

Start with ROOT-RECEIPT.json, candidate-final-source-sha256.json, standards/REPORT.md and spec/final-typecheck-bridge/REPORT.md. Earlier Spec source pins are superseded only by the final bridge. REDs, rejected hypotheses and failed setup receipts are retained and classified in the release record. No deployment is asserted.

Bulk frozen source copies and build dependencies stay outside Git. Complete source manifests and the committed baseline/candidate preserve identity. Historical commands/scripts are evidence with absolute local cache paths, not new portable product tooling. SHA256SUMS covers retained files.

The local .gitattributes disables line-ending normalization for this evidence
directory so Git preserves the original captured bytes and their hashes.
Captured output also retains its original trailing whitespace; the scoped
whitespace attribute applies only to this evidence directory.
