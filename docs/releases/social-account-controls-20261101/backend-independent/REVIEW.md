# Independent backend account publishing review

Approved for the local backend scope. Final normal and optimized executions each passed **147 tests, zero failures/errors/skips** against identical source hashes before and after execution. This includes 81 reviewer cases (74 direct/HTTP boundary cases and seven actual PostgreSQL migration/concurrency/fault cases) and 66 author account/manual/media/material cases. Full XML and stdout are retained as `final-normal.*` and `final-optimized.*`.

Three genuine findings were reproduced before fixes and re-executed green:

- Deferred account/receipt effects could commit a stale positive account DTO. The final transaction witness now compares full durable state after deferred settlement and exact receipt persistence. Four PostgreSQL trigger cases pass.
- Suppressed audit insertion could produce accepted consent without an audit event. The final account witness now checks the exact stored audit event and details. SQLite and PostgreSQL suppression probes reject and roll back.
- Malformed non-object TikTok capability metadata prevented retrieving status and pausing. A typed context guard now reports unavailable admission while preserving explicit pause. Five persisted malformed shapes pass.

The initial numeric `eligible: 1` allegation was a reviewer-fixture error: ORM JSON equality considered the valid original `true` equivalent and skipped the write. Explicitly persisting and rereading an integer proves the existing strict admission rejects it. No native admission source fix was needed. Historical raw failures are retained and are not counted as product findings.

Distinct-intent PostgreSQL contention produced exactly one commit and one version conflict. Same-key contention produced one audit and one receipt. Strict direct and HTTP inputs, authorization, unknown account/missing schema, metadata fences, ABA/stale requests, replay conflicts, historical replay after disconnect, unresolved delivery ownership and Page/parent credential expiry boundaries were executed. Replays remain historical receipts; they neither reapply consent nor prove present account readiness.

The PostgreSQL fixture used actual migrations in random owned schemas on a disposable cached PostgreSQL17 container with no network access or published ports. The database used tmpfs and the container was removed. Python/package versions, exact source/test hashes and XML counts are in `REVIEW.json`. Reviewer changes are confined to this evidence directory. No source/index/branch/GitHub/production changes, live credentials, provider calls or publishing/uploads/workers were used. These results do not establish deployed behavior or full-suite acceptance.
