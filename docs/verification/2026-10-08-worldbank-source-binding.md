# World Bank economic source binding — 8 October 2026

Refs #506 and the broader #137 acceptance work.

## Change

The economic World Bank producer now registers its canonical API acquisition URL as the source document URL, consistent with the national GDP producer. The human-facing indicator page is preserved in the existing persisted notes. No writer/schema changes or qualifier domain aliases are introduced.

This is a prospective producer correction. Existing shared source documents, historical evidence and numeric values are not rewritten. Existing observations do not gain stronger evidence merely because code is merged; a separately scoped refresh must produce valid new receipts.

## Executed proof

The pre-fix integration failed because sealed, byte-matched API acquisitions were classified `conflicting / receipt_request_source_mismatch` for all seven economic indicators. The national GDP path registered the API source correctly.

After the fix, the regression exercises the actual economic fetcher, parser and writer; owned file SQLite; the actual R2 SigV4 adapter with HMAC-checked synthetic storage; and the FastAPI economic response. All seven freshly acquired observations qualify as verified, their human citations remain in persisted notes, and the pre-existing landing-page source document remains unchanged. Changing the acquired request host to a foreign host still produces seven source conflicts. Public handlers perform zero source-storage requests.

Coordinator run: **148 passed, 3 existing deprecation warnings in 3.10 seconds** across the new integration, figure qualification handlers and receipt ingress trust tests. `git diff --check` passed. Dotenv was disabled, the database destination was an owned SQLite file, and no real credentials, publisher requests or production SQL writes were involved.

The reproduction and red/green logs are retained in the local coordinator evidence directory. This receipt does not claim live publisher acceptance, production-row counts or storage rollout completion. Those are separate #137 gates.
