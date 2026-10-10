# backend/seeding/config.py financial-literal context review (#602, 2026-10-10)

Scope: only the `backend/seeding/config.py` entry of
`backend/tests/financial_literal_reviewed_inventory.json`, as granted by
ISSUE_602_DECISION_001. Every other entry (including #603's `backend/main.py`)
is untouched.

| File | Reviewed base | Base source SHA-256 | Reviewed source SHA-256 | Context AST SHA-256 |
|---|---|---|---|---|
| `backend/seeding/config.py` | `bcb5ff99854de595bbe3f7d60cc8796b7ada5a20` | `ecc99f91c6d7015c0bace8bb9c92bf27390f8617f4935a06d7ee6c3debb7cb72` | `a8889d3e27846064120bfef259184384c42dd411bcd0897117fc91e87152bd1c` | `8fe7603217e27de72746cdf8ee349f41efb6846982dfcb8230610a4cd1cd8e9d` |

The only delta from the accepted base is the #602 opt-in field
`cra_ingestion_enabled: bool = False` and its `explicit_cra_opt_in` validator
(accepts only `bool` or the strings `"true"`/`"false"`). It carries no numeric
literal, reads no other setting and is consumed only by
`seeding/registries.py:load_builtin_domains`, `admin_etl_dispatch_adapter.ready_domains`
and `seeding/domains/cra/__init__.run`, all as a boolean gate.

## Raw sites (scanner output on the reviewed bytes)

`find_invented_figures` reports exactly one site, the same signature as at the
base (its line moved 408 -> 420 because of the inserted field):

- `audits_county_start_budget_seconds=240` — disposition unchanged:
  reviewed contextual value, #301.

## Callers, publication and fallback context (re-read on the reviewed bytes)

- Consumers: `backend/seeding/domains/audits/__init__.py` lines 546 (copied into
  `volume_report["start_budget_seconds"]`), 562 (national discovery admission),
  627 and 634 (county-volume / older-document admission). All compare elapsed
  `time.monotonic()` seconds or disclose the threshold in scheduling metadata.
- Publication: `volume_report` is stored at line 897 as job metadata
  (`metadata["county_volumes"]`). `grep` over `backend/routers`, `backend/main.py`
  and `frontend/lib` finds no reader of `start_budget_seconds`/`county_volumes`;
  it never becomes an audit, budget or revenue amount.
- Fallback: none. A deferral records processing state (`deferred`,
  `reason: start_budget`); no default figure is substituted for a missing value.
- The new CRA field does not reference this setting, and no new use of 240 was
  added anywhere (no new caller in `backend/` or `etl/`).

Conclusion: the single site keeps its prior disposition. Only the context AST
digest and review pointer of this entry change; signature, reason, disposition
and tracking are preserved byte-for-byte.

Executed controls: `tests/test_apis_no_invented_national_figures.py` and
`tests/test_batch9_financial_review_context.py` (including the config
"new financial use" mutation) — receipts are listed in the #602 handoff.
