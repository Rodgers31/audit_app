# OAG combined-volume catalogue availability

Date: 2026-10-31. Scope: #802, combined county executive/assembly availability only.

The official OAG RSS catalogue can state a full timestamp for an exact document
entry even when the signed PDF gives no publication day. A later PDF replacement
can retain the same entry, so its timestamp cannot establish PDF publication.

Accept an explicit `publisher_catalogue` record only when retained official RSS
bytes bind one exact PDF URL, a reviewed complete title and GUID, a full timestamp,
and an independently extracted complete PDF title page with the same institution,
volume and annual fiscal period. Store the timestamp as `catalogued_on`, retain
`published_on=null`, and keep the original PDF acquisition separate from current
job-bound retained-byte revalidation. The executive and assembly series have
separate identities. Existing per-series selection/current-authority guards apply.

The caption must name the institution and period, say the report's publication
date is unknown, require human review and lead to AuditGava. Catalogue evidence
cannot create financial authority or enter automatic approval/scheduling/
publication. No financial audit adapter is introduced.

Missing/ambiguous feed entries, different PDF URLs, short or inferred dates,
conflicting cover scope, subperiods and unsupported title spellings refuse.
No date is borrowed from feed build time, a URL/upload directory, retrieval,
signature, tabling or another report. Unknown official evidence stays unavailable.

This extends the existing explicit KRA catalogue distinction to a separate,
narrow OAG contract. It is not a generic catalogue/date fallback or proof that
all production OAG volumes qualify. The current local acceptance covers the four
exact FY2022/23 and FY2023/24 executive/assembly pairs; five other retained
production documents still lack matching evidence. Operational financial
generation, publishing, uploads and workers remain off.
