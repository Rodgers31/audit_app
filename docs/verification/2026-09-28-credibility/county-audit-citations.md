# County audit list page citations — issue #359

Implementation commit: `92df632c152e3d0db61badecc7a5c258ce482af5` on `codex/county-audit-page-citations`, based on `a7faedb509b63e8ac68557bf90456cb6f2828629`.

## Change and contract

`backend/main.py::list_county_audits` now parses `Audit.page_ref` with the existing `services.audit_citations.page_number` convention and exposes the first positive page as `source.page`. It also exposes `source.page_url` via `report_page_url`, which retains query parameters and other PDF fragment settings while replacing an old `page` setting. The enhanced API fallback uses the same normalization. Malformed, zero, and negative textual references yield `source.page: null`; absent references remain withheld by the database publication gate. An invalid URL yields `source.page_url: null`. `AuditListWithSources` follows the resolved URL, checks its HTTP(S) protocol, and opens the document URL without constructing a page when talking to an older API that lacks `page_url`. The existing source title, fiscal period, and `publishable_audit_criterion()` query remain in place.

The additional response field is `items[].source.page_url: string | null`. The frontend type marks it optional for an older API response. This component is currently unmounted in the frontend tree; see the finding below. No schema or stored record changed.

## Red and green evidence

All backend pytest commands used `PYTHON_DOTENV_DISABLED=1`, explicit local `DATABASE_URL=postgresql://auditgava_dev:auditgava_dev@127.0.0.1:55432/auditgava_local_dev`, `REDIS_URL=''`, `TESTING=true`, `AUTO_SEEDER_ENABLED=false`, and `AUTO_WARMUP_ENABLED=false`, with `/Users/roger/Documents/projects/audit_app/backend/.venv313/bin/python`. The test fixtures create isolated in-memory SQLite tables; the local PostgreSQL URL is only an import-time engine target and was not connected for these tests.

- Before the fix, `python -m pytest backend/tests/test_county_audit_list_citations.py -q -x` failed at the public API boundary: `assert source["page"] == 2` received `None` for a synthetic published `page_ref="p. 2"`.
- Before the fix, `npm --prefix frontend test -- --runInBand --watch=false __tests__/components/AuditListWithSources.test.tsx` failed two link assertions: the rendered target ended in `#page=9&zoom=100#page=2` or `#page=pp. 38-39`, rather than replacing the existing page fragment.
- After the fix, targeted `backend/tests/test_county_audit_list_citations.py`, `test_audit_findings_source_url.py`, and `test_audit_endpoints.py`: **32 passed**. The new integration fixture checks single and range pages, malformed/negative/zero and absent references, another county, fiscal-year filtering, the fallback response, and an unsafe URL.
- After the final frontend edit, the component Jest suite: **5 passed**. `frontend/node_modules/.bin/tsc --noEmit --project frontend/tsconfig.json`: exit 0.
- A local synthetic fixture API on `127.0.0.1:18104` returned `source.page: 2` and `source.page_url: https://example.invalid/auditgava-local-audit.pdf#page=2` for the published Nairobi finding. Headless Chromium set an anchor from that returned value and resolved its target to the same URL with exactly one `#page=2` fragment. The temporary fixture server was stopped. The `example.invalid` PDF is synthetic and cannot verify an external publication.

## Remaining acceptance

This commit is local, not merged or deployed. Production records and source PDFs were not read or modified. The coordinator should verify the combined branch and deployed endpoint, then check a real stored, published finding against its actual source PDF before claiming public citation acceptance. The UI link test covers this component only; its current lack of a route caller means it does not establish a visible county-page link.

## Additional findings for coordinator triage

1. **Wrong-county list when the mapped county has no entity row.** `backend/main.py:5951-5960` applies the entity filter only when `entity_ids` is nonempty. In the unchanged local synthetic fixture, `GET /api/v1/counties/042/audits/list` (Kisumu, absent from that fixture's entity table) returned Nairobi's synthetic finding with HTTP 200, total 1. This can misattribute another county's finding. The equivalent Nairobi request returned that same row, confirming the fixture's identity. This is outside #359's citation change. No exact open issue was found in targeted GitHub searches for wrong-county audit lists; #359 is the related endpoint issue.
2. **Some invalid textual locators pass the publication gate.** `backend/services/publication_gate.py:142-168` excludes blank and bare zero-like strings but accepts `p.0`, `p.-3`, and `p.38 garbage 73`. The new API fixture confirms all three rows are listed by `publishable_audit_criterion()` while `services.audit_citations.page_number` returns `None`, so the response honestly lacks a precise page. The gate also intentionally permits valid nonnumeric locators such as `Annex VII`; a repair must preserve those. Related broader provenance issues: #137 and #322; no exact open issue was identified in targeted searches.
3. **The fixed UI component is not mounted.** `rg -n 'AuditListWithSources|useCountyAuditList|getCountyAuditList' frontend --glob '!node_modules/**'` found the component, hook, API function, and the new test, but no app route or other production component importing `AuditListWithSources`. Thus the new link behavior is verified at component and browser-target level, not on a public county page. Issue #359's UI acceptance needs a caller or a separate visible-page verification, coordinated with the owner of the county page.
