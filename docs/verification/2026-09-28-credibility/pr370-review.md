# PR #370 citation parser review

Base: PR head `6fa3d1cef58f9a38a212b8f37f5ec187d5a203b7` (`origin/codex/credibility-api-evidence`). Review branch: `codex/pr370-review`. Fix commit: `f7e83bfdc10146ebac9e2c38f4dbeecdb2673234`. No push or PR action.

## Classification and fix decision

Copilot [comment 4128209028](https://github.com/Rodgers31/audit_app/pull/370#discussion_r4128209028) is **valid**: `citation_page` used `[IVXLCDM]+`, which accepted noncanonical `Annex IIV`, `Schedule VX`, and `Appendix IIII`. The suggested canonical validation is appropriate. The implementation checks conventional Roman notation from I through MMMCMXCIX (1–3999) for multi-character Roman identifiers; it still permits single alphabetic identifiers and positive decimal identifiers. Prefixes (`Annex`, `Annexure`, `Appendix`, `Schedule`) are case insensitive, whitespace within a label is normalized, and the explicit compact `Schedule12` control is supported. Named locators remain text; `page_number` still supplies numeric pages and range starts. No relevant ADR or decisions file was found by a scoped `rg` search; the prior county citation receipt described named locators without a Roman grammar decision.

The suggested fix was judged separately from the finding: the comment proposes canonical syntax but no patch. A standard Roman grammar at the shared `citation_page` choke point covers both the database and enhanced API list paths (`backend/main.py:6002,6073`), while leaving `report_page_url` and its default/opt-in fragment behavior untouched. The list response keeps invalid labels as `source.page: null` and removes stale `#page=9` while retaining `#zoom=100`.

## Executed evidence

Backend commands used `PYTHON_DOTENV_DISABLED=1`, explicit local `DATABASE_URL=postgresql://auditgava_dev:auditgava_dev@127.0.0.1:55432/auditgava_local_dev`, `REDIS_URL=''`, `TESTING=true`, `AUTO_SEEDER_ENABLED=false`, and `AUTO_WARMUP_ENABLED=false`, with `/Users/roger/Documents/projects/audit_app/backend/.venv313/bin/python`. Pytest fixtures used isolated in-memory SQLite; no PostgreSQL connection, production database, or source PDF was accessed.

- **Red on PR head:** `python -m pytest backend/tests/test_county_audit_list_citations.py -q --tb=short` produced `4 failed, 10 passed`. Each of the three Copilot examples was incorrectly returned as text, and the real county list API returned `source.page='Annex IIV'` instead of null.
- **Additional red control:** after adding exact `Schedule12` support to the test, the parser and list API both returned null for that string (`2 failed, 13 passed`). The PR-head grammar required whitespace even though the review brief named `Schedule12` as a positive control; the fix supports it explicitly.
- **Green:** `python -m pytest backend/tests/test_county_audit_list_citations.py backend/tests/test_audit_findings_source_url.py backend/tests/test_audit_endpoints.py -q --tb=short` returned **51 passed**. Checks include invalid `IIV/VX/IIII`, additional malformed Roman forms, canonical additive/subtractive and upper-bound forms, one-letter and decimal labels, numeric pages/ranges, both API list paths, and stale PDF fragment handling. `git diff --check` passed.

## Limits and adjacent findings

This review changes only the county-list citation parser and tests. It does not change the broader publication gate, whose malformed-locator behavior is tracked in [#366](https://github.com/Rodgers31/audit_app/issues/366). The compact `Schedule12` discrepancy was corrected in this commit; no further confirmed adjacent defect was found in the scoped review. Production acceptance and PR integration remain with the coordinator.
