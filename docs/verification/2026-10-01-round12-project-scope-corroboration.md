# Project narrative scope: new OAG comparison, 1 October 2026

The bounded investigation adds a **historical identity candidate** for Nyamira's
Speaker's Residence. It does not resolve the FY2025/26 paid-value conflict or
justify adding a project row, OAG reference, or current audit-verification label.
Keep [#230](https://github.com/Rodgers31/audit_app/issues/230) open. The
[comparison manifest](2026-10-01-round12-project-scope-corroboration.json) pins
the four retained PDFs and exact pages inspected.

## Nyamira: Assembly identity, older observations

The [FY2023/24 OAG County Assemblies volume](https://www.oagkenya.go.ke/wp-content/uploads/2025/02/GREEN-BOOK-ASSEMBLIES-2024-FINAL-01-April-2025-KLB.pdf#page=207),
PDF207 / printed193 / paragraph537, concerns Nyamira's Assembly Speaker's
Residence. Its contract is **KES34,377,805**, commenced **6 February 2023**,
with an expected completion date of **6 August 2024**. A **28 May 2024** status
report records **77% completion** and **KES24,158,208 paid**. September2024
inspection found unfinished work; the audit raises value-for-money concerns,
not a finding that the whole contract/payment amount was proven lost.

Those details align with the [CoB annual FY2025/26 narrative](https://cob.go.ke/download/county-governments-budget-implementation-review-report-for-the-financial-year-2025-26/?wpdmdl=16482),
PDF686 / printed652: Assembly Speaker's Residence, Bonyamatuta Ward,
February2023 start, estimated **KES34.38 million**, **77% completion**, and
as-at **30 June 2026**. The OAG contract rounds to the CoB estimate; the
institution, name, start month and percentage agree. This is an inference of
likely historical identity. OAG paragraph537 does **not** give the ward or a
shared contract/tender identifier. Its observations concern an older period.

The new comparison does not select between CoB's **KES26.62 million paid**
summary/Table2.6 and **KES26.65 million paid** named narrative. Nor may the
older **KES24,158,208** replace either annual value. Paragraph533, PDF205 /
printed191, separately reports **KES2,457,540 pending payable** for the
residence; a payable is not a second paid amount or authority to balance the
later statements.

An arithmetic-only comparison gives 24,158,208 + 2,457,540 = **26,615,748**,
rounding to **26.62 million**. This combines older paid and pending measures;
neither paragraph says the pending payable became paid. The rounding alignment
does not validate CoB's annual payment statement or resolve its conflict.

The [FY2024/25 OAG County Assemblies volume](https://www.oagkenya.go.ke/wp-content/uploads/2026/05/AUDITOR-GENERALS-REPORT-ON-COUNTY-GOVERNMENTS-COUNTY-ASSEMBLIES-2024-2025-1.pdf#page=229),
PDF229–230 / printed216–217 / paragraph621, carries the residence delay in
its unresolved FY2023/24 issues table. It supplies no fresh residence monetary
observation. Paragraph632, PDF232–233 / printed219–220, concerns a separate
**Assembly offices block**, with a KES367million contract; do not join that
finding to the Speaker's Residence.

The FY2024/25 Executive chapter, PDF604–618 / printed591–605, has seven
separately named stalled projects under paragraph1262, PDF606–609 /
printed593–596. It contains no Speaker/Bonyamatuta match. Executive totals
cannot corroborate the Assembly residence or fill the county's annual count.

## Siaya: exact name still uncorroborated

CoB PDF758 / printed724 names completion of **Nyamonye Juakali**, **Yimbo
East**, as at **30 June 2026**, value **KES1.88 million**, paid **KES3.72
million**, under investigation. The narrative attributes reporting to the
county, but does not explicitly identify the implementing institution. Do not
infer that from adjacent departmental rows. CoB's national prose PDF45 /
printed11 describes overpayment; that publisher statement and an investigation
do not establish an OAG finding or proven loss.

The [FY2024/25 Executive volume](https://www.oagkenya.go.ke/wp-content/uploads/2026/05/AUDITOR-GENERALS-REPORT-ON-COUNTY-GOVERNMENTS-COUNTY-EXECUTIVES-2024-2025-1.pdf),
Siaya PDF542–555 / printed529–542, and Assembly volume, Siaya PDF200–203 /
printed187–190, contain no Nyamonye/Jua Kali name match in extracted text.
The positive control is Executive paragraph1134, PDF548 / printed535:
**Nyabera Primary School ECDE block**, KES4,307,957 contract, stalled in
July2025. This is a different named project and period; no amount or finding
from it is transferable to Nyamonye. The check is bounded to these chapters,
not proof that no report anywhere concerns Nyamonye.

## Decision and evidence boundary

No corrected annual source or explicit same-period/amount clarification was
located. Fresh public GETs of the CoB annual download page, consolidated
listing and OAG FY2024/25 listing returned HTTP200 at approximately **21:39
Chicago on 1 October** (02:39UTC, 2October). The annual page still displays
25September2026 creation/update; the OAG listing supplies FY2024/25 volumes,
not a FY2025/26 observation. These HTML checks do not certify that remote PDF
bytes remain unchanged. Local retained PDFs match the accepted source hashes.
Official-domain searches for the exact names/amounts and an annual corrigendum
found no resolving source; this is a search limit, not exhaustive absence.

The existing table parser constructs detail rows from captioned tables
(`cob_parser.py:1137–1142`); the writer iterates those rows
(`writer.py:219–220`). Named narrative extraction is an extension needing a
maintainer contract, rather than a demonstrated dropped table row. Any future
contract must distinguish the reporting body from implementing institution,
keep the two Nyamira payment statements, qualify Siaya's investigation, and
retain separate dates and amount bases for any historical OAG link. A match
must never turn older audit concern into verified current loss/status.

Only the new comparison is recorded here. Existing 168 detail rows / 47 county
records, 188 observed summary counts and reported189 remain inherited
[Round11 evidence](2026-10-01-round11-county-source-reconciliation.md#projects-reported-totals-versus-detail-table-scope),
not new extraction or production acceptance. No parser/writer/service/data/UI
change, application import, database connection, full suite or PDF replay ran.
Source-only checks verified hashes, page counts, exact positive controls and
bounded text absence; eight rendered pages were inspected. Reproduce with
the external `ROUND12_SESSION_5_SOURCE_CHECK.py` and its retained log/captures
beside the session handoff. Production cleanup/ingestion, publication and
Projects exposure retain their separate owner/maintainer gates.
