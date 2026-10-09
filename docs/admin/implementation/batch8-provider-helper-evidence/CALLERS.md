# Legacy helper and exception inventory

Inventory command (repository-wide Python, pinned base plus lane diff):
`rg -n 'supabase_admin|SupabaseAdminError|get_profile\(|get_profiles\(' --glob '*.py'`.
Exact output is retained as `caller-search.log` in the external lane directory.

| Entry/consumer | Actual contract and coverage |
| --- | --- |
| `backend/supabase_auth.py` package/top-level imports; `_fetch_roles` → shared `get_profile` | Only product caller of retained profile reads found. Catches `SupabaseAdminError`, uses no body/text/status; absent/failed profiles yield no admin roles. Independently checks UUID identity and role array. Real signed JWT + memory transport positive and malformed/error controls execute this consumer, including both fresh import modes. No auth policy/JWKS/JWT code changed. |
| `backend/admin_users_provider.py` | Imports shared exception, `_config`, `_headers` in both modes; has its own transport and profile helpers. Already raises body-less 503/502 or provider status. New shared constructor retains class identity/status. Active transport/fresh imports and all 164 retained Users cases are exercised. Implementation is outside this lane. |
| `backend/routers/admin_users.py` | The name `supabase_admin` aliases **admin_users_provider**, not the legacy module. `_provider` reads only `.status_code` for 404/429/503 and otherwise 502; static responses. No `.body` or exception text consumer. Retained route/private error controls execute this wrapper. |
| Other legacy public functions: auth user list/read/update/delete/recovery, role update and count | No product callers found outside the helper/auth inventory. Public compatibility functions remain. Actual memory calls exercise successes, HTTP and transport failures; role acknowledgment/header/count controls remain. Role transport errors deliberately now raise safe shared 503 instead of raw HTTPX errors. Only that related old test expectation changed. |
| Tests/browser fixtures | Synthetic providers and shared exception construction, profile/count overrides, baseline helpers and import controls. No trusted raw diagnostic requirement found. AST `.body`, request/response `.body`, and fixture payload fields elsewhere are unrelated objects. |

Searches also included `.body` and exception handlers across backend Python.
The only shared exception body assignment was its constructor; other `.body`
uses were AST/HTTP/test fixture/user-feature values. No repository consumer
requires raw provider diagnostics. The compatibility constructor argument and
`.body` attribute remain; body is deliberately discarded and always `None`.
No trusted diagnostic escape hatch is added.

The protected invariants are requested profile identity/array membership and
status-only ordinary exception diagnostics. Both single and bulk reads pass
through one validation boundary. `_raw_request` protects all its public helper
paths; count has a separate HTTP path with the same safe failure translation.
The shared exception constructor protects active provider and direct fixture
construction too. Other auth user mutation/URL and count header/filter contracts
are outside #570; no parser, writer, publication or financial changes are made.

No import or product call to the retained helper was found outside these entries
in the repository search. This does not assert absence of external consumers.
