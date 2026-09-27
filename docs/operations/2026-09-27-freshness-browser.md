# Freshness and browser release receipt — 27 September 2026

Session 5 starts from `dc58685bb72007a5654863bfbeee912cfd6b89e3` on isolated branch `codex/honest-freshness-browser-ci`. Implementation is prepared for review. Production acceptance remains open; this task performed no production seed, cleanup, secret change, deployment or merge.

## Contracts

- **Badge (#295):** every requested publisher must be present with a recognized verdict and a valid, nonfuture ISO publication date. Duplicate COB cannot stand in for Treasury. Partial, malformed, missing and failed responses are neutral. Server HTML gives `Freshness unknown`; hydration can show a temporary checking state. The group date is the oldest member's publication date, displayed in UTC so a date-only value does not move back a day for American readers.
- **Source evidence (#322):** registration, verified download, extraction and publication are separate. `/sources/summary` retains registered document count and `last_seen_at`, and adds downloaded/extracted counts. `last_fetched` uses a successful HTTP 200, complete MD5 and nonfuture verification timestamp, not the obligatory registration `fetch_date`. These transport fields are intentionally conservative: older writers without verified transport bookkeeping show “Not verified.” An extraction count does not certify complete coverage.
- **Publication freshness:** `/data/freshness` dates only accepted domain rows linked to that named publisher; it never borrows another publisher's global observation maximum or a newly registered report's date. It uses explicit complete ISO publication metadata, never fetch-date fallback. Audits use the existing public audit gate; other models use their stored `publishable` flag. This does not expand the seven-table publication policy in #137 or certify OAG institution/county completeness; Session 4 owns that coverage gate. Debt coverage uses sourced timeline observations, not loan contract issue dates. Unknown source aliases stay unknown; combined publisher declarations are not silently split into independently verified publishers.
- **Monitoring (#294):** a configured critical URL becomes actionable when bounded retries are exhausted in that run. This is deliberately earlier than a three-night counter; no indefinite “transient” exemption or new persistence layer. Timeout, denied HTTP codes, connection failure, incomplete transfer, and not-probed remain separate report outcomes. Auto-close requires completed probes, measured success for every critical URL and no unprobed source. Its wording certifies transport only, not extraction/publication.
- **Refresh (#231):** the existing signed sequence is reused: seed and validation succeed → API invalidation → frontend revalidation. Receipts require exactly one JSON document, boolean `invalidated: true`, and the exact requested page list with no rejection. API GET responses default to `Cache-Control: no-store` because browser/intermediary HTTP caches cannot participate in backend invalidation. Backend caches still serve normal reads. Already-open React Query views retain their normal stale windows; the tested contract is a new visit/reload after refresh, not live push updates.
- **PR CI (#291):** `Browser publication acceptance` builds production Next.js and runs the bounded Chromium acceptance directory against the real FastAPI app with isolated synthetic SQLite records. It is required by the quality gate. No production credentials or publisher connections are needed. The original historical multi-browser suite remains separately runnable; it is not represented as green.

## Executed reproduction and verification

Local commands use the task's `.venv` and shared installed frontend packages. The working directory for the backend suite must be `backend`, as in CI.

Final branch verification: **5,370 backend tests passed, 24 existing skips** (`python -m pytest tests -q --ignore=tests/integration`); **67 frontend suites / 732 tests passed**; TypeScript and lint passed; **8/8 Chromium acceptance tests passed** against the production build and isolated real API. The full backend run includes the malformed receipt, HTTP 204, publisher-alias and future-date regressions. Jest reported its existing open-handle notice after passing, then exited successfully. These are local receipts; GitHub CI results are recorded on the draft PR.

| Boundary | Before correction | After correction |
|---|---|---|
| Partial/duplicate publisher and no-JS badge | 6 failed / 17 passed | covered by 34 badge tests |
| Registration/fetch vs accepted publication and HTTP caching | 6 failed | controlled accepted old/current, genuine-zero, registration-only and download-only cases pass |
| Critical retry exhaustion and false recovery | 3 failed | bounded local HTTP probes pass |
| Malformed refresh receipts | 4 failed / 6 passed | exact-shape and single-JSON receipt regressions pass |
| Adversarial malformed dates/publishers/digests | reproduced false freshness and a huge-integer date crash | strict parsers/aliases and positive controls pass |

The local end-to-end test changes only a synthetic Nairobi budget from KES100B to KES125B in a disposable database. It first proves the old API response remains cached. Missing secret and wrong signature stop before page revalidation. It executes the **actual `seed.yml` shell steps**, confirms backend invalidation precedes frontend revalidation, reads the new API figure, blocks client county API fetching and reloads the actual county page. The rendered table changes to 125B using refreshed server data without restarting or deploying either app.

A separate combined rehearsal temporarily included Session 1's corrected `DebtPageClient.tsx` and its three `e2e/acceptance/debt.spec.ts` tests. **11/11 Chromium checks passed**, including valid nominal ratio/dated DSA separation, absent ratio without recomputation, genuine zero, county period selection, partial/complete/stale/unavailable freshness, no-JavaScript badge, and signed refresh. The Session 1 component and test were removed from this branch after rehearsal; their owning PR supplies them. CI discovers that acceptance file automatically after integration.

### Retained unsuccessful checks

These failures are test/environment evidence, not hidden skips:

- First browser run: expected `0.0%`, but the real table renders `0%`; corrected the test to the visible contract.
- First refresh attempt with JavaScript disabled: after on-demand ISR, the first response's Next.js streaming/loading shell did not expose the county table. The final refresh proof uses a normal browser with client county fetching blocked, so only server-provided data can supply the changed value. The no-JavaScript **badge** behavior is tested separately on `/budget`; full no-JavaScript county browsing is not claimed.
- First broad backend invocation from the repository root: one subprocess could not import `cache`; two route guards required a newer FastAPI than the borrowed local 0.129.0 installation. Corrected invocation to `backend` and installed the compatible FastAPI in this task's isolated environment only. The primary checkout/environment was not modified.
- Legacy `e2e/debt.spec.ts`, with unchanged main debt component and the fixture API: **1 passed, 4 failed**. Failing names: `national debt page shows key stats and charts`; `"Where every KES 100" card uses the fiscal-summary ratio (about KES 78, tax + non-tax revenue)`; `debt page exposes a methodology disclosure with the total-debt-service calculation`; `debt page source line names the ratio inputs explicitly`. The old fixture/expectations do not establish the current fiscal/source contract. No blanket skip was added. These remain outside the new bounded acceptance gate, under #291.

Logs are retained locally as `/tmp/session5-*-red.log`, `/tmp/session5-*-green.log`, `/tmp/session5-browser-combined.log`, `/tmp/session5-legacy-browser-baseline.log`, plus final suite logs. Independently executed adversarial probes are under `/tmp/session5-freshness-adversarial`, `/tmp/verify_seed_workflow.py` and `/tmp/raw_refresh_probe.py`.

## Production readiness and serial ingestion

The launch receipt verified `REVALIDATE_SECRET` absent from Actions, Render and Vercel (including linked groups/shared variables). A fresh `gh secret list` during this task still showed it absent from Actions. The owner was asked to generate one dedicated value, enter the same value in all three destinations and apply the environment changes. Do not paste it into a task, a PR, an issue or logs. Browser credential-entry policy requires owner handoff; do not rotate the separate newsletter `SECRET_KEY`.

Configuration destinations:

1. GitHub repository Actions secret: `Rodgers31/audit_app`, name `REVALIDATE_SECRET`.
2. Render service `srv-d6hr3t5m5p6s73bomqu0`: the same environment value, applied to the running backend.
3. Vercel project `rodgers31s-projects/audit_app`: the same server-only production environment value, applied to the serving deployment. It must not be `NEXT_PUBLIC_*`.

After configuration and review/deployment prerequisites, verify a bounded signed cache invalidation and frontend receipt, then select **one** approved publication manifest. The constant workflow concurrency group already serializes shared production seed jobs; no additional job was dispatched here. Do not dispatch from unreviewed session code or run speculative all-domain seeds. Domain writers still need exact selected source versions/hashes, row/dependency plans, recovery and before/after API/browser receipts. A restart or TTL expiry is not accepted as the requested without-deployment refresh proof.

| Session | Current release handoff |
|---|---|
| 1 national finance | Draft #341 includes the consumer and CBK document-identity fixes and three debt acceptance tests. Domestic CBK replay alone is insufficient to authorize full `national_debt`, which also reconciles external loans and bonds. Await full plan and deployed writer correction. |
| 2 sourced records | Draft #340 protections precede population refresh. Row79 repair is separate from broad cleanup. Regenerate cleanup snapshots after shared source writes. |
| 3 county finance | Annual CoB artifact preflight underway; preserve partial coverage and explicit zeros. Await final manifest and reviewed/deployed publication guards. |
| 4 county audits | Current-period clone receipts are not production coverage. Await final bounded volume manifest, institution/period coverage receipt and deployed guards. |
| 5 freshness | Local refresh proof passes; production remains configuration/release blocked. No job slot is granted until its prerequisites are verified. |

Issues #231/#295/#294/#291/#322 remain open for their applicable review, merge and production conditions. No automatic closing keywords are used by this draft.
