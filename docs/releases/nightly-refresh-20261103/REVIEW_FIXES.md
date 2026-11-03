# Review corrections for PR #903

The parser's insertion count is not always its current finding inventory. Blue
Book reconciliation reports `findings` together with created, retained and
updated rows. County-volume extraction already reports its complete current
inventory in `created`; cached paths report `skipped` or `existing`. One pure
counter contract now validates these shapes for both the document boundary and
the refresh summary. The document boundary still compares the outcome with
retained database rows and validates the current source/parser stamp.

Loading now accounts for every processed row as created, updated or explicitly
unchanged. Existing row identity, text, financial values and provenance retain
their original meaning; unchanged rows do not inflate update counts. Missing,
malformed, inconsistent or unaccounted inventory refuses completion.

Single-county reports use their explicit county schema, existing COUNTY entity,
country and fiscal year. They cannot create national ministries. References
include county, report role, section, subsection and paragraph. Fresh validated
extraction stamps the source digest; cached evidence with a missing or stale
stamp refuses pending source review. Present fetched-PDF identity is verified
before and after reading, and mixed rejected CID evidence refuses before writes.
This does not grant single-county rows county-volume PDF bindings or native
financial source authority.

The national banking fixture intentionally stubs the loader; its `schema: test`
rows do not reach the real loader. The two cited banking tests pass in both
Python modes. Its synthetic parser/load counters now explicitly describe the
current inventory and unchanged rows. Separate tests exercise the real parsers,
loader and refresh consumer, with retained IDs and financial values checked.

Red/green regression receipts and the independently qualified combined release
are retained outside the repository in the release-903-905-20261103 evidence
packet. No production source acceptance, nightly rerun, publishing, uploads,
workers or financial generation is authorized by these local checks.
