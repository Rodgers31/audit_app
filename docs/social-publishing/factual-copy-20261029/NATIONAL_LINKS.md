# National and report destinations

New generated posts lead to AuditGava first. Qualified source identity, reporting period and a semantic snapshot select the exact public view; original publisher links remain supporting citations on that page.

| Source | Current version and destination |
|---|---|
| Qualified county/national budget, revenue, audit or pending-bills report | `report-availability-v4` → AuditGava `/reports/{domain}/{document_id}` with the exact source selectors and snapshot |
| Catalogue entry with unknown publication date | `catalogue-availability-v4` → the source-bound AuditGava view, retaining the catalogue date, unknown publication day and human-review requirement |
| Native national budget/revenue financial observation | `financial-v5` → the exact AuditGava figure view; figures, date and qualifications remain bound to the source |
| County pending-bills observation | `financial-v5` → the exact AuditGava county pending-bills figure view, with the real county identity and reporting day |
| Other general facts | `factual-v3` → the supported on-site evidence destination |

The backend reader is supplied by #852 and the frontend report page by #853. Both must ship in the complete reviewed release tree; either child PR alone is an incomplete product package. Unchanged qualified reacquisition preserves the snapshot URL. A genuine correction gives the new evidence a new snapshot; the old exact view returns unavailable rather than substituting a new value or period.

Earlier external-link report/catalogue V3 and national financial V4 revisions remain readable and render their original bytes. They are historical contracts, not current defaults or permission to publish an external destination. Publication rechecks resolved master/account caption destinations and requires AuditGava. Template and policy scopes remain version-specific; saved drafts are not rewritten by deployment.

Offline tests exercise actual qualified writers, PostgreSQL, the public HTTP reader, selectors/snapshots, same-date corrections, frontend decoding and account previews. This proves the local complete-tree contract, not provider connectivity or production adoption. See the [combined release review packet](../../releases/admin-social-20261029.md) for deployment dependencies, validation and holds.
