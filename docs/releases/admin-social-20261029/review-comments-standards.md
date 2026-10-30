# Independent Standards review — PR review follow-up

Status: **scoped pass — 118 independent controls passed, zero skips; no actionable finding remains in this review scope**. The reproduced P2 below is fixed and independently rechecked. This offline review does not authorize deployment, publishing, workers or source admission.

## Provenance

The final input is immutable `source-final/`, copied from integration HEAD `a21a99e7b64c27ca83b424d3f8285d29802d61aa` plus current review fixes. All 2,271 listed backend/frontend entries match `source-final-manifest.json` after execution. Manifest file SHA256: `eef1226fefb9b79d82195b9ae0bbd5758b4547749d49cadf0e4b753e45af2826`. The scoped backend/public-client/page boundary hashes also still match the author checkout. Exact test/result pins are in `final-provenance.json`; changed paths are listed in `source-final-delta.json`.

The original red input remains in `source/`, with manifest SHA256 `81e5073bacac0026637e9335f968d4a3c0e02aee2868d089a461eac90c04c04e` and `pin1-provenance.json`. The only backend product delta from red to final is the TikTok UTF-16 fit branch; social_copy.py is unchanged. The final snapshot also carries the author's unrelated BudgetTab/Composer/navigation/translation changes: this review does not assert coverage of those changes. The extra copied Git pointer supports Next's configuration lookup and is not product input. `accepted-head/` retains accepted editorial/social-copy files for executable legacy comparison.

Cached runtimes: Python image `sha256:571e327e2fbe507713d267f6f15050d585a5bbb53b8ec2e3afc73db2996d6d2d`; Node image `sha256:199a2e300b058b48b009358105fa1749007be613917893abc008d9d50ae991f3`, locked dependency volume `admin-redesign-locked-deps`. Every project process ran with `--network none --cpus 1 --memory 2g --pids-limit 256`, source mounted read-only. No PostgreSQL, external provider, publication, worker or production action was used. SQLite databases were process-local test fixtures. Validation provider fixtures recorded zero calls.

## Resolved finding

**P2 — generated TikTok caption can pass editorial fit and fail native length validation.** `backend/social/generation/editorial.py:158–163` counts TikTok captions using Python code points; `backend/social/adapters/tiktok.py` enforces UTF-16 units. A strictly valid observation whose title and first fact's metric, comparison basis and publisher each contain 300 `🧾` characters produces a 1,444-code-point caption containing 2,644 UTF-16 units. Editorial fit returns true; the actual native adapter refuses it with `CAPTION_TOO_LONG` against its 2,200-unit video limit. This prevents the promised ready caption. The downstream refusal remains closed; the test does not demonstrate unauthorized publication.

Exact reproduction: `test_editorial_attacks.py::test_astral_metadata_never_produces_an_over_limit_ready_tiktok_caption`. Red receipts: `pin1-editorial.txt`, `pin1-editorial.xml`, `unicode-measurement-final.txt`. The final fit calculation counts TikTok UTF-16 units and returns false for invalid Unicode. The **unchanged** original hostile case now passes through the actual native validator (`final-editorial.xml`). Four direct exact-limit/invalid-surrogate controls additionally reproduced three failures on the original input and pass on final (`pin1-limits.xml` → `final-limits.xml`). Other platform fit rules are unchanged.

## Executed controls

| Lane | Executed | Result | Receipt |
|---|---:|---|---|
| Editorial generation → actual target resolution → native TikTok validation | 20 | 20 pass | `final-editorial.xml` |
| Direct UTF-16 exact-limit and invalid-surrogate controls | 4 | 4 pass | `final-limits.xml` |
| Actual FastAPI router/service, persisted SQLite source identities, HTTP serialization | 27 | 27 pass | `final-public-python.xml` |
| Actual TypeScript decoders/API functions and async report page/consumer | 67 | 67 pass | `final-client.json` |
| Total | 118 | 118 pass; zero failures, errors or skips | `final-replay.json`, `limits-replay.json` |

The original full replay remains 113 pass/1 reproduced failure in 114 cases (`pin1-replay.json`); the later four direct guard controls remain separately red on the original input. Original red evidence was not overwritten.

Editorial controls execute factual, financial, report and catalogue families: exactly one primary URL in the resolved TikTok caption, explicit null link override, native validation success for ordinary inputs, and unchanged evidence. Facebook/Instagram/Threads/X retain the master link field. Long on-site URLs either fit the actual TikTok validator or explicitly refuse. Captured TikTok defaults discard per-post consent; without fresh consent the real validator refuses `TIKTOK_CHOICES_REQUIRED`. Unchecked source schema/title/empty-facts mutations refuse. Current factual-v3 leads handle singular/plural titles; factual-v2 output is compared byte-for-byte with the accepted implementation for four titles, and factual-v1 still renders.

Public controls run the actual router and service with real owned SQLite SourceDocument/BudgetLine rows. Wrong document/record/entity combinations refuse before any source qualification reader. Changed facts/period/entity/document/checksum and uncommitted, fixture, quarantined or unpublishable results refuse with 410; unavailable operational readers return 503; response details hide internals. Successful responses are `no-store`, contain only the public DTO, and issue no application writes. These selected qualification readers are explicitly stubbed prequalified observations: this proves selector, transport and privacy behavior, **not current PostgreSQL source authority**. The integration owner separately owns genuine current-PG reader/witness execution and PostgreSQL read-only transaction enforcement; SQLite only emulates that transaction-control syntax here.

The exact successful HTTP JSON is passed into the actual frontend decoder and API adapter, then rendered through the actual asynchronous Next page and ReportView. It preserves scope, exact figure values, basis and original source link. Unsafe URLs, malformed numeric strings/types, schema/selector/figure-header mismatches, duplicate/unknown query parameters and empty sources refuse. Refresh failure hides cached data and exposes explicit unavailable/retry; invalid selectors make no request.

**PR853 negative-total claim is refuted.** Source-page totals `-1`, `-25`, `-1000` and malformed/non-finite/unsafe-integer values refuse in `decodeSourceRecords`; the actual `generationApi.sourceRecords` boundary also refuses the three negative totals and mismatched selectors. Empty and 1,000-record boundary pages retain their exact meaning. This pagination contract is distinct from signed exact financial figure strings, which the shared typed figure contract and public decoder intentionally allow; no generic negative-money decoder change is justified by these tests. Native monetary qualification is a separate source boundary.

## Replay and limitations

From the host, run only the stdlib orchestrator (all project code executes inside the owned offline containers):

```sh
python3 /Users/roger/.codex/visualizations/2026/10/29/01a1886d-f9ce-70c1-8bdf-14a2bb51c304/admin-redesign/release-rollout-20261030/standards-review/run-review.py --source source-final --label independent-replay
```

That command replays the 114 core controls. The four direct guard controls' exact capped Docker argv, source selection, exit code and JUnit pins are retained in `limits-replay.json`; invoke its final command to repeat them. Using `--source source` deliberately reproduces the original Unicode failure. The script refuses receipt overwrite and records exact argv, child exit code and log SHA256 in the label's replay JSON. No network, download, installation or image build is needed. Native PG authority, actual provider execution, browser paint/layout, concurrent source acquisition, deployment and production hold states are outside this review's executed scope.

All own containers were transient `--rm` executions and have completed. This review created no PG containers or credential environment files; no root/other-agent fixture was stopped or changed.

Initial exploratory logs are retained, including setup-only failures: the SQL write audit initially included deliberate fixture installation, an operational exception used an unsupported constructor keyword, and one supposedly hostile report selector was valid. These were corrected in external tests before final lane results; no product change or skip hides those failures. `unicode-measurement.txt` retains an exploratory measurement's missing optional-override error; the corrected measurement is separately labeled.
