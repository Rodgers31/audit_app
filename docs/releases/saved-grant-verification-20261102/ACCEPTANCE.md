# Saved Meta grant verification with delivery paused

Candidate based on `2e206ed9974b254adf75b44867915e326d54487c`. This is local engineering acceptance, not a deployment or a live grant-validation receipt.

## Result

The existing authenticated verification command now receives a separate saved-grant authority. It exposes only inspection and close, checks validated app identity and pinned Graph version, and admits bounded GETs to the exact verification endpoints/fields. OAuth exchange, delivery endpoints, method overrides, request bodies, foreign origins and unsupported versions refuse before underlying I/O. Saved verification no longer requests additional Page access tokens during Page discovery.

Provider identity, scopes, Page tasks, linked Instagram identity, credential lifetime, privacy and concurrent-state checks remain required. Provider reads hold no SQL transaction. Proof, controls version, audit and idempotency receipt still commit together with a deferred durability witness.

Without an accepted native adapter, successful verification records `eligible=true`, `adapter_available=false` and restricted publishing. The account and global publishing controls remain paused. Installing an adapter later cannot silently upgrade this proof: explicit re-verification is required. The existing fully accepted native path retains its separate admission checks.

## Executed validation

The cached deployed backend image is `sha256:28a15896d429f8ad645011d98c5c406582557766f7cc2ab9b16c4ed2c1ce74b8`: Linux amd64, CPython 3.12.16, 81 installed serving distributions. Candidate source was mounted read-only with a separate test-only overlay. No dependencies were installed in that image.

| Lane | Normal | Python `-O` | Scope |
| --- | ---: | ---: | --- |
| Connections, saved verification, account controls and native admission compatibility | 612 passed | 612 passed | Intercepted provider HTTP and isolated SQLite |
| PostgreSQL commits, concurrent changes and receipt-time corruption | 10 passed | 10 passed | Eight new verification cases plus two existing connection races; owned ORM schemas |
| Current migration and database-role controls | 13 passed | 13 passed | Owned PostgreSQL 17; migration/RLS/browser-default checks |

The 13 role cases initially skipped inside the serving container because Docker was absent there; the dedicated assigned-fixture runs execute those exact cases. Each mode has **635 distinct passing cases and no unresolved skips**. Modes and overlapping reviewer compatibility runs are not added together.

Two independent executable reviews cover private hostile-input controls and actual mounted API composition. Their final source-bound receipts are summarized in `VALIDATION.json`. One reviewer found accepted method-override headers at the final transport guard. Six author regression cases reproduced the failure before the explicit three-header refusal; the reviewer independently confirmed the fix. This establishes the local transport boundary, not whether a live provider honors those headers.

Raw logs, JUnit, commands, source hashes, producer scripts, initial failures and final review manifests are retained in the attached local `verification-authority-20261102` evidence directory. The initial Sentry compatibility failure was a container import-path error. The first PostgreSQL corruption fixture used `route` instead of `route_key`; only the fixture changed. Neither was waived as a passing check.

## Remaining production acceptance

This change does not establish that the real saved Facebook or Instagram grants are valid. After review and deployment, run one bounded, idempotent verification command for each exact account and retain its receipt. Refusal must remain visible; a successful restricted proof does not accept native delivery, media custody/restore, worker capacity, callback privacy or operator launch gates.

Publishing, uploads, workers and financial generation remain off. This work makes no production configuration change, no provider request, no media upload, no deployment, no ingestion-pin update, no hosted test dispatch and no paid review request. Existing deployment automation and branch rules are unchanged.

## Client-contract review correction

PR review identified a real missing client boundary: the browser required `enable_available=true` even for successful restricted verification. The client now also accepts exactly the sole `NATIVE_ADMISSION_UNAVAILABLE` blocker, while preserving paused account, exact identity, control-version increment and changed state-token requirements. Other or mixed blockers still refuse. The rendered control explains the saved permission proof, refreshes account state and keeps enabling disabled until delivery setup and explicit re-verification are complete.

Two actual React/client cases reproduced the failure before the fix. The corrected source passes 986 frontend tests, full TypeScript checking and scoped lint. Two independent executable reviews pass with no findings. `CLIENT_REVIEW.json` binds these receipts separately from the earlier backend acceptance; it does not claim live provider or deployment evidence.
