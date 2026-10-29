# National and report destinations

Opening `/budget` from a FY2025/26 report showed the public page's default FY2026/27. That page has no supported year selector in its URL. New generated drafts now use the qualified original publisher source instead of sending readers to a different year.

| Source | New version and destination |
|---|---|
| Published county/national budget, revenue, audit or pending-bills report | `report-availability-v3` → exact `report.document_url`; “Read the original report on the publisher’s website.” |
| Catalogue entry with unknown publication date | `catalogue-availability-v3` → exact entry `document_url`; the copy names the entry and preserves the unknown publication date/human-review requirement |
| Native national budget/revenue financial observation | `financial-v4` → exact first fact's qualified `document_url`; “Read the original source on the publisher’s website.” All facts must still have the same source identity |
| County pending-bills observation | Unchanged `financial-v3` → actual county slug, source day and pending-bills section |
| Other general facts | Unchanged `factual-v2` → canonical evidence destination |

This applies to the source family, regardless of county name. It creates no guessed URL, new public endpoint, report extraction or inferred findings. Exact evidence, semantic event fingerprints, qualification, current worker witnesses and human-review boundaries remain intact. Stored drafts are not rewritten.

Saved report/catalogue V1/V2 and financial V1/V2/V3 copy still renders using its original version. The policy gate compares both text and link using that immutable version, and scopes remain version-specific. A V1/V2 snapshot cannot acquire V3 authority merely because the code was upgraded. Direct helper calls also revalidate Python-mode source inputs and reject unsupported or foreign template families.

Tests execute native writers with retained source evidence, source selection, preview/detect/save, current authority checks, historical policy replay, malformed URL/schema/numeric cases and actual frontend decoding/preview. These are offline owned fixtures. They verify destination identity and year, not continued availability of an external publisher's web server or its download presentation. The local comparison examples remain clearly labelled illustrative data.

See the [combined release review packet](../../releases/admin-social-20261029.md) for counts, baseline failures, deployment order and holds.
