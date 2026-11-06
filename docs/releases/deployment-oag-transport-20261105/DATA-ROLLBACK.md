This plan prepares data rollback; it does not execute or authorize adoption.

The local packet contains complete business before-values for all 813 extraction IDs and exact dependent audit associations/digests. Complete source metadata, extraction DB columns/created_at and audit/fact before-image bodies were not transferred. A checksum cannot reconstruct missing rows. An executable production rollback is therefore held until these before-images and a real rollback rehearsal exist.

Before any authorized adoption:

1. In the same serialized source transaction, read and retain complete SourceDocument2392 JSON, all813 original oag_blue_book extraction rows including every DB column/created_at, all814 source/dependent audit rows, and actual other referencing facts from a catalog FK census. Compare exact current row bodies/IDs/hashes with this proposal; changed inputs refuse and require regeneration.

2. Keep a private bounded full before-image bundle plus row schema/type/role/source/job/runtime identities and a per-row checksum. Existing seven-day local database-export policy remains unchanged; this lane supplies no retention exception.

3. During an authorized adoption, record exact allocated new extraction/audit IDs, all updated/retired rows, source metadata and before/after hashes. Map additions by the actual blue_book_row_key(vote,paragraph_no,title), additionally bound to source and fiscal year; no guessed IDs or count-only rollback.

4. Verify rollback in an owned database with full before-images, actual constraints and unrelated rows preserved before any production data acceptance.

To undo that exact adoption:

1. Lock the source and exact affected IDs. Refuse if current after-images, lineage or concurrent later observations differ from the authorized adoption ledger.

2. Remove only newly inserted audit/fact rows and new finding extraction IDs whose exact source/job/after-hash match the ledger. No broad DELETE by source and no cascade across other domains.

3. Restore retired original extraction IDs and complete revised extraction before-images, then complete changed audit/fact before-images and references. Preserve audit902 and every unchanged/unrelated row.

4. Restore only adoption-owned source/current-extraction/publication metadata from complete before-images. Retain genuine immutable pdf-receipt-v1 original/revalidation evidence and retained originals independently; do not delete truthful acquisitions because content adoption was rolled back.

5. Check all exact extraction/audit/source/fact hashes, FK/identity constraints and the unchanged audit902; commit only the verified restoration. Cache/page readback is a separate later authorized workflow action.

The exact private retirement/revision IDs, dependency inventory and source/proposal hashes remain in acceptance-packet-v1/data-rollback.json (SHA256 7e4276f55a290a31646e5a8b0c61c0b504316a5bf23042b587aac7cd51cee858). Complete computational row dispositions: SHA256 46137e7e0e63e7fd05046c2dd88a2da8ec89b81137ebf577304e969a88179c5b.

Code reversion alone does not reverse adopted data. No rollback/adoption, DDL, cache invalidation or production mutation was performed by this lane.
