# Prospective PDF evidence (#137)

This intake changes future PDF ingestion. It does not certify or backfill existing rows.

## Recorded evidence

The parser records each observed measure, source geography and reporting period,
physical PDF page, table/cell, raw amount, printed scale and explicit transformation.
The acquisition receipt retains the source byte digest separately from the normalized
row hash. A raw-cell manifest is sealed before persistence; writers compare the row
identity/value with that manifest and allocate real `pdf-receipt-v1` Extraction IDs.
Configured JSON datasets cannot supply successful PDF ingestion envelopes.

Storage uses the shared `ReceiptStore` contract and the explicitly local CAS adapter.
A completed full HTTP 200 stream records the actual response metadata and decoded
bytes. Cached receipts preserve their acquisition time. Local files, old cache entries
without acquisition metadata, and assembled partial responses do not invent transport
success. Source bytes changed beneath a recorded digest remain a contradiction.
No durable production adapter is selected by this change.

## Writer scope

| Producer | Observations |
| --- | --- |
| County CoB budget tables | Printed allocation and expenditure cells, including continuation pages |
| County CoB cash receipts | Direct printed Grand Total target/cash cells; stream sums remain qualified without operand evidence |
| National annual CoB sector summaries | Revised gross allocation and expenditure Total cells |
| National quarterly CoB sector tables | Net allocation and exchequer issue cells; existing proxy declaration stays explicit |
| Treasury BROP pending bills | Published MDAs/State Corporations outstanding balances and stated as-at date |
| County CoB year-end payables | Reported county Grand Total outstanding balances; missing/withheld counties stay absent |
| CBK bulletin instruments | Outstanding stock by published month; principal/interest/terms receive no inferred certification |
| CBK bulletin debt timeline | External/domestic/total source amounts; GDP and ratios require separate operand evidence |

The seven-table reader contract also covers maintained API/web sources. This PDF lane
does not invent PDF producers for GDP, poverty or economic series. KRA receipt work
belongs to the separately coordinated API/web producer lane.

## Local verification and remaining gates

`backend/tests/test_prospective_pdf_evidence.py` exercises actual parsers and writers
against two owner-approved retained documents when these paths are supplied:

- `PDF_EVIDENCE_REAL_BROP`: Treasury BROP 2026, SHA256
  `39c2e290ecdb6be0d8768344514711a5b0c6a350f0416ed81e529cded60def24`.
- `PDF_EVIDENCE_REAL_CBIRR`: CoB FY2025/26 annual county BIRR, SHA256
  `5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`.

The county budget test extracts physical pages 43/44 only; the year-end payables
parser follows the report's table-of-contents locators. No publisher network request
is made. These retained files have unknown original HTTP acquisition metadata and
therefore remain qualified. Owned HTTP controls test acquisition mechanics; they are
not publisher observations. Retained national CoB/CBK bulletin bytes are unavailable
in this lane; their existing publisher text fixtures and parser controls do not replace
that gate. Cross-lane consolidation, durable storage, fresh operational intake and
deployed public acceptance remain owner gates.
