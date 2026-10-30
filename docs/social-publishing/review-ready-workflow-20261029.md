# Prepared social posts

Implemented for owner PR review. Publishing, workers, hosted workflows and deployment remain held. This replaces the earlier product-gap brief; the final executable receipts and any remaining rollout conditions are in [the release review packet](../releases/admin-social-20261029.md).

## Admin workflow

Qualified structured sources create saved drafts containing a readable caption, an AuditGava destination, original source references, relevant hashtags and configured account variants. The reviewer can inspect each account preview, attach optional media, review the checks and explicitly approve/post when the separate publishing controls are enabled. Ordinary generated posts require no caption writing, hashtag research or link repair.

Account selection/defaults are configured once. Instagram receives an image draft and TikTok a video draft where a text default would be unsupported. Adding inspected media selects an implemented compatible format, preserves copy/citations and automatically saves and validates the exact new revision. Unknown or incompatible formats stay visible and held. The inert format catalogue is not publishing eligibility or provider access.

Generated drafts open to the preview on mobile. Editing is available. The explicit **Refresh caption & hashtags** action prepares a new revision from a current verified generated source, retaining master/account media and immutable history. It refuses stale or unavailable source evidence; it does not invent a newer source or mutate an approved/published history entry. It is an authenticated idempotent command returning the complete new post detail.

Media-specific rights, TikTok privacy and creator consent remain explicit review checks. The engine cannot attest ownership, music rights or descriptions of unseen media. Account defaults cannot carry another post's consent into a generated post.

## AuditGava first

All accepted post destinations and caption links lead to HTTPS AuditGava. The rule is checked after account overrides resolve, during validation and again before worker dispatch. A legacy external-link revision remains readable as history but cannot publish through old approval authority. Original publisher URLs remain permitted as secondary source references.

New county pending-bills posts bind the exact county, reporting date and figures through the qualified source record. Supported county/national financial and report families use `/reports/{domain}/{document_id}` with source-bound selectors. The public reader supports county budget figures/reports, national budget, revenue, audits, pending-bills reports and publisher catalogue records. Unsupported source families retain their established on-site destination; no publisher URL fallback is used for a new package.

The page identifies entity, period, publication/catalogue date, attribution, exact and compact figures where present, qualifications and original citations. Public requests use a bounded, read-only, repeatable-read transaction and an explicit response allowlist. They do not query private social drafts, account settings, source events or workflow history. The source-authority digest views used by existing county readers contain public source bindings, not social editorial records.

Selectors bind public meaning and document checksum rather than ingestion attempt IDs. Unchanged reacquisition keeps a link valid. Changed, withdrawn, quarantined, missing or mismatched evidence produces an unavailable response instead of another year/entity/latest report. Catalogue records keep an unknown publication date. The client rejects inconsistent figure/header scope and never relabels another entity's amount.

## Project-owned editorial engine

Production reads `backend/social/generation/editorial-policy-v1.json` and executable repository code. Local Codex skills informed these rules; production does not need a developer's skills directory or an AI/model API. No model, paid service, live trend scraping or new network call is introduced.

Tags are selected from verified measures, report topic and actual geography. Examples include `#PendingBills #MombasaCounty`, `#PAYE #Kenya`, `#HealthBudget #Kenya` and `#PublicAudit #Kenya`. Revenue heads and budget sectors receive different tags. Location spelling comes from source identity; no Nairobi special case is used. A restrained brand tag fills available account slots. Claims of wrongdoing, unrelated trends and engagement bait are never inferred.

The current policy selects up to two tags for Facebook/X, three for Instagram/TikTok, and one native Threads topic. X's two-tag choice follows its official recommendation. The Facebook, Instagram and TikTok counts are conservative AuditGava editorial choices, not asserted platform maximums or reach guarantees. Meta direct help/documentation access was limited during this review; its official Postman Threads collection independently documents `topic_tag`. Threads sends its topic through that native field rather than duplicating a hashtag block in the caption. Existing delivery, consent, visibility and paid-access gates still apply.

Sources for maintenance: [X hashtags](https://help.x.com/en/using-x/how-to-use-hashtags), [X authenticity](https://help.x.com/en/rules-and-policies/authenticity), [Meta Threads API collection](https://www.postman.com/meta/threads/documentation/dht3nzz/threads-api), [TikTok sharing requirements](https://developers.tiktok.com/doc/content-sharing-guidelines/).

The policy records review date, review deadline and reference status. New preparation stops when review is overdue (27 January 2027 for V1). Engineers review the official contracts, update/version the repository policy and rerun the tests; the admin does not research hashtags per post. A model would not make performance claims current by itself. Performance-driven optimization would require separately admitted, verified account analytics; this release makes no promise of trend prediction or maximum reach.

## Evidence and authority

The complete package is reproducible from source evidence, template version, policy hash and captured account profiles/hash. New defaults are factual V3, financial V5, and report/catalogue availability V4. Prior renderers remain for exact historical replay. A new template/policy cannot inherit an older automatic policy scope. Human edits and media changes require ordinary current-revision review.

Captions preserve exact evidence and distinguish display rounding with “about”. Short numeric variants retain attribution and every relevant financial caveat. When that meaning cannot fit, the account gets a neutral entity/topic/period invitation without an amount, or an explicit hold. No numeric claim is made more confident by shortening it.

Validation and preview resolve the same account content; dispatch rechecks the frozen payload. Auto-save cannot continue into validation after the composer unmounts or its admin session changes. Failures retain the draft and explicit save/validate recovery controls. No automatic approval, scheduling or posting occurs.

## Local review

The loopback review harness contains five engine-rendered illustrative samples: Nairobi pending bills, Mombasa pending bills, national budget report, PAYE revenue and national health budget. AuditGava post links open matching local source pages in this explicitly labelled harness. Amounts and evidence are illustrative; the harness is not source verification or a production draft update.

One repository image demonstrates library selection and preview using an isolated harness substitute. Production upload/storage validation remains unchanged and strict. The harness refuses delivery, approval and control mutations; uploads and workers remain off. Actual image/video composer persistence, format selection and validation are separately exercised by executable tests.
