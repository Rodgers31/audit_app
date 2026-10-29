# Admin task map and acceptance ledger

Base: accepted main 7797ecb4266169c438ecd2c82e6d817d6577ff19. Implementation uses an owned managed checkout. No production deployment or activation is included.

## Product direction

Roger reviews important new public-finance evidence and prepares clear posts. The interface should feel like a source-backed editorial desk: post first, supporting record close by, operations available contextually. Domain: reporting periods, county figures, retained publisher reports, human review, delivery receipts. Forest ink, paper, pale sage, copper warnings and restrained gold focus retain AuditGava's identity. The signature is the post/evidence pair with explicit human approval and a separate delivery state. Compact headers replace decorative public-page heroes inside private work.

The local Pro Max search returned Minimalism/Swiss hierarchy, contrast, keyboard and reduced-motion recommendations that fit. Its Hero + Features + CTA pattern, Fira Code headings and blue/pink palettes do not fit this task and were rejected. Narrow disclosure search still returned only Heading Line Balance: **no verified disclosure match**; disclosure uses the loaded cognitive-load/interface-design rules and native HTML details. Next.js results describe 16.2; this project is 15.5.28, so the suggestion to migrate mutations to Server Actions was rejected. Existing authenticated FastAPI contracts stay in use.

Responsive decision: the queue stays a readable vertical list. The composer uses side-by-side writing/preview only with sufficient room; mobile has explicit editor/preview controls. Optional tools remain keyboard-operable native disclosures. No modal or new dependency is needed.

## Verified routes and tasks

`page.tsx` inventory under frontend/app/admin; callbacks are route handlers, not invented pages.

| Route | Task and current friction | Essential/contextual controls | Acceptance status |
|---|---|---|---|
| /admin | Find work needing attention; technical summaries compete with next steps | Overview links and truthful partial/errors; diagnostics contextual | Shared header/navigation implemented; task content review pending |
| /admin/users | Find a person and inspect access | Search/pagination; role operations contextual and authorized | Shared shell implemented; inner flow pending |
| /admin/users/[userId] | Inspect person, change authorized access | Identity and roles; reasons and audit history | Shared shell implemented; inner flow pending |
| /admin/ingestion | Inspect completed data updates and separate draft outcomes | Jobs, filters, source/outcome links; operator details contextual | Shared shell implemented; outcome UX pending |
| /admin/ingestion/[jobId] | Understand ingestion vs generation, refused evidence and partial execution | Job facts and generation outcomes; source/lineage diagnostics | Shared shell implemented; cohort repair pending |
| /admin/etl | Run or recover a bounded native task | Availability, selected source, preview/dispatch reason; policy/worker prerequisites contextual | Shared shell implemented; ordinary consumer remains OFF |
| /admin/etl/commands/[commandId] | Track exact command and recovery | Receipt, job/result, safe recovery; idempotency/lease diagnostics | Shared shell implemented; inner flow pending |
| /admin/audit-log | Find who changed what | Filters, event details, pagination; raw payload contextual | Shared shell implemented; inner flow pending |
| /admin/social | Find a useful draft and open review | Review/in-progress/attention queues, contextual filters/history, direct draft link | Implemented and qualified in first increment |
| /admin/social/new | Write, preview and save a manual post | Text, link, destinations; settings/media/overrides contextual | Implemented and qualified; regression coverage includes title, nested errors and account recovery |
| /admin/social/[postId] | Edit post → preview → evidence → next review action | Immutable revision, factual attestation, safe command/retry semantics; scheduling/archive/diagnostics contextual | Implemented; independent Spec and Standards scope accepted |
| /admin/social/automation | Explain draft preparation, baselines and policy | Existing qualified adapters, preview, controls, outcomes; raw IDs advanced | Shared shell implemented; everyday source selection pending |
| /admin/social/accounts | Inspect connection vs delivery readiness | Current account capability and paused state; connection/privacy recovery contextual | Shared shell implemented; inner flow pending |
| /admin/social/accounts/callback | Return from Meta connection | Existing callback security and safe recovery; no new page needed | Functional handler preserved, no reconnect authorized |
| /admin/social/accounts/platform-callback | Return from alternate provider | Existing ingress hold and recovery; unsupported readiness explicit | Functional handler preserved |
| /admin/social/media | Inspect retained assets | Library and details; uploads unavailable while held | Shared shell implemented; inner flow pending |
| /admin/social/studio | Graphics, calendar and analytics | Existing source/render selection and timezone/delivery evidence | Shared shell implemented; rendering/collection held |
| /admin/social/privacy | Inspect privacy and retention | Existing review/recovery controls, explicit current authority | Shared shell implemented; inner flow pending |
| /status | Check system and source status | Existing guarded status contract, unknown distinct from healthy | Compact private header implemented; inner flow pending |

## Verified gaps

- Existing but confusing: duplicated social navigation, long public hero with route IDs, queue plus embedded full composer, exposed shadow rules/checksums before post, unrelated operations beside review. Addressed in first UI increment.
- Existing but broken: automatic 46-county hook times out after partial baselines (#849). Owned PostgreSQL automatic-hook fixture reproduces timeout after partial baselines; product repair and qualification remain pending.
- Required but missing from normal flow: source selection resolved from an eligible committed job without pasted IDs; actionable link from no-draft outcome to the existing exact source context. Verify server selection contract before implementation.
- Required writing change: shared factual renderer exposes internal metric/basis/unit wording. Reusable versioned deterministic copy is next after #849, not hand-edited Nairobi content.
- Optional later: new networks, broader media generation and marketing calendars. Not acceptance criteria here.

## Held and unproven

Publishing, uploads, social/native/supervisor workers, ordinary admin consumer and financial automation remain OFF. No new hosted ingestion, production backfill or real draft is authorized. Green ingestion alone cannot certify draft generation or delivery. Local fixtures never establish production acceptance. Full original admin completion is not claimed.
