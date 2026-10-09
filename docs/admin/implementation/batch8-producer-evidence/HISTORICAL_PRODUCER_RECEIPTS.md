# Historical producer receipts — current-generator supersession

Recorded 2026-10-09. The `native_pdf` and `native_worldbank` receipts in
`docs/verification/2026-10-08-r2-actual-acceptance.json`, and their citations in
`docs/verification/2026-10-08-r2-storage-acceptance.md`, describe the prior
executed Linux producer. They remain historical evidence; their original
reported values and source hashes are preserved without alteration.

Status: **SUPERSEDED for claims about the current generator**. Old generator:
`backend/scripts/r2_producer_acceptance.py`, SHA256
`15b2a796171a9bd8b994d1de16bc8a4e49b863a57dc85dd77baa78395aad1028`.
New generator SHA256:
`9124c3c8abad7b48c8ed78d580c01012662174fd1ca4b5bdd148cc0250a1478f`.
The only source change clears captured dictionary contents instead of deleting
the closure binding, at the same pre-SQLite boundary.

The old PDF receipt reported 935 pages, 1,129 tables, 468 records, 378 cell
evidence entries, one SQLite receipt extraction and 1,404 qualification fields.
Those complete PDF/parser/memory/time/hosted results are **unverified for the
new generator**, because this lane has not acquired or replayed the exact
53,561,211 retained bytes with SHA256
`5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`.
The new bounded synthetic runtime controls prove capture, conversion, release,
local-byte receipt authority and real SQLite/public qualification behavior;
they do not refresh the old retained semantic oracle or hosted acceptance.

No cited financial number was changed and no correction to the prior execution
is asserted. A new full replay would require the exact retained bytes, reviewed
runtime/oracle, owned storage/SQL, and separate operational authorization where
applicable. The existing disabled workflow deliberately still pins the old
generator and refuses the new bytes. Its pin requires a separate reviewed
coordinator update before any future authorized invocation. The pin and Actions
state are outside this lane's edits.
