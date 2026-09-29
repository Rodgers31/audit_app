# County Explorer health grades and regions — #349 / #350

Implementation commit: `b6876e29db97d38d3775c1c03795731213cbc156` (base `a7faedb509b63e8ac68557bf90456cb6f2828629`, branch `codex/county-grades-regions`). This receipt is a separate follow-up commit.

## Behavior and method

- The financial-health index uses the backend bands in `backend/main.py:964`: **A ≥85; B+ ≥70; B ≥55; B− ≥40; C below 40**. `frontend/lib/counties/financialHealth.ts` supplies the letter, map fill, badge style, sidebar/legend choices, and detail modal scale. It rejects absent, non-finite, and out-of-range scores. The accountability scale remains separate in `CountySignals.tsx` and the accountability tab.
- The Explorer's map, legend, sidebar filters, rankings, best/worst panel, and regional average now use that scale. The average is displayed and graded to one decimal, matching the backend's score precision. Ungraded counties remain visible as unavailable and are excluded from best/worst claims. When no county is scored, the panel says so.
- `frontend/lib/counties/regions.ts` uses a shared normalized county name for API records and GADM paths. It strips the optional `County` suffix and punctuation, so the 47 current API names and the map's space/hyphen variants resolve to one former-province region. `Nairobi City` remains an explicit alias. Unknown names resolve to `null` rather than an invented region.
- The detail modal now describes the current weighted composite (budget absorption, own-source revenue, pending bills, audit opinion) and the two-component minimum, rather than the retired utilization-only formula. Related numbers are labelled as context; the API does not expose a per-county component breakdown in this payload.

## Red → green evidence

All test commands used an empty `REDIS_URL`, explicit local SQLite `DATABASE_URL`, `TESTING=true`, `AUTO_SEEDER_ENABLED=false`, `AUTO_WARMUP_ENABLED=false`, and dotenv disabled. No production environment or database was used.

- At base, `npm test -- --runInBand __tests__/countyExplorerGradeRegions.test.tsx __tests__/countyDetailRedesign.contracts.test.tsx` failed **4 of 15** tests: no B+ map/legend band despite a 76-point B+ readout; `Unknown (NaN)` average; Coast returned five rather than six; detail modal still said `Score = utilization percentage`. The same tests passed after the fix.
- Before the adjacent unavailable-state fix, `npm test -- --runInBand __tests__/countyExplorerGradeRegions.test.tsx -t 'does not call an ungraded county'` failed: “Needs Attention” showed ungraded Mombasa instead of scored Kwale. It passes after the fix.
- Before the average precision fix, `npm test -- --runInBand __tests__/countyExplorerGradeRegions.test.tsx -t 'classifies the same rounded average'` failed: the 84.9/85.0 example did not show `A (85.0)`. It passes after the fix.
- Final focused frontend run: seven suites, **106/106 tests passed** (grade/region, detail, map readout, sort controls, signals, county API and absence). `tsc --noEmit`, targeted ESLint, and `git diff --check` passed. `backend/tests/test_county_financial_health.py`: **26/26 passed** under the same local environment.
- Dedicated tests cover 0/40/55/70/85/100 boundaries, 76 and 45, missing/NaN/infinite/out-of-range scores, unknown names, six alias spellings, and all 47 intended region memberships.

## Local browser evidence

Used the isolated synthetic SQLite API on `127.0.0.1:18103` and Next.js on `127.0.0.1:13103`. A browser-only interception of the *selected-year county list* supplied nine explicitly synthetic counties for map/filter verification; the fixture API supplied the detail page. These values do **not** assert real county amounts.

- At 1440×900, selecting Coast showed **six counties**, including Taita Taveta. The synthetic filtered summary was KES 20.0B, including Taita Taveta's synthetic KES 6.0B; its map link/readout/legend agreed on B− and its fill was `#b36b5c`. The map zoom included its polygon. [Desktop screenshot](./county-grades-regions-desktop.png).
- At 390×844, the B− map filter left one interactive Taita Taveta polygon and one county in the summary; document horizontal overflow was **0 px** at both widths. [Mobile map screenshot](./county-grades-regions-mobile-map.png).
- The synthetic Nairobi detail page showed the current composite explanation and a separate accountability badge. [Methodology screenshot](./county-financial-health-methodology.png).

## Acceptance and limits

This is a frontend code correction. It changes no stored figures, ETL, source citations, publication gates, or deployment configuration. It has **not** been deployed or verified against the production 47-county response. Before closing #349/#350, the coordinator should verify the deployed commit, current API county names, Coast's six memberships and filtered totals, and score/grade agreement on the live Explorer and detail page. Production figures need their own source reconciliation; the synthetic budget values above are test fixtures.

## Additional finding for coordinator triage

**Per-county health components are omitted from the comprehensive response.** `county_financial_health()` returns each component, weight, share, and score (`backend/main.py:1127-1134`), but the comprehensive response writes only `health_score` and `grade` plus unrelated ratios under `financial_summary` (`backend/main.py:4572-4599`). A bounded local fixture request to `/api/v1/counties/001/comprehensive` returned `health_score: 45.0`, `grade: B-`, and keys `[budget_execution_rate, debt_sustainability, grade, health_score, pending_bills_ratio]`; `components` was absent. A reader can see the general methodology but cannot reproduce the individual score from the page. The same function's docstring still calls the composite “equal-weighted” (`backend/main.py:1034`) although the executable weights at `backend/main.py:997-1004` give the audit opinion weight 3. This may fit a follow-up to #349 or the broader provenance issue #137; no new GitHub issue was filed by this worker. Production exposure and exact component provenance remain to be verified by the coordinator.
