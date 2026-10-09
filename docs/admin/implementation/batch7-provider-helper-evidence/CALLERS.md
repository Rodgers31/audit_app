# Pinned caller inventory and retention

Baseline: `f0ea1bbd41f33e7666cf2b7fbc4cc4abcfe60b0d`, tree `712b43650b1203ffd84583b67d07d30775669b1e`.
The complete tracked tree was searched with:

```sh
git grep -n -E '_raw_request|update_profile_roles|count_profiles|admin_users_provider|supabase_admin'
```

The full output is hashed in the external evidence manifest. The product-only Python search was also retained; this inventory precedes the new helper tests.

| Entry path | Existing behavior / coverage |
| --- | --- |
| `backend/supabase_admin.py:_request` | Delegates to `_raw_request`; public `list_users`, `get_user`, `update_user`, `delete_user`, `generate_recovery_link` all have direct memory-transport controls. |
| `get_profile`, `get_profiles` | Direct `_raw_request` reads without per-call headers; single/bulk transport and empty-bulk controls pass. |
| Legacy `update_profile_roles` | Only legacy production definition; no product caller/import of this function was found. Its internal per-call Prefer was the duplicate keyword entry path. |
| Legacy `count_profiles` | Separate single-header GET; no product caller was found. Count 3 and filtered `{admin}` controls pass before/after; function is unchanged. |
| `backend/supabase_auth.py:55,59,209` | Package/top-level module imports and actual signed-token `get_current_user` -> `get_profile` transport are preserved. |
| `backend/admin_users_provider.py:11,13` | Imports shared `SupabaseAdminError`, `_config`, `_headers`; its own transport/role helper remains read-only. Both import modes execute its real memory transport. |
| `backend/routers/admin_users.py:18,19,347` | Aliases **active** `admin_users_provider`; role mutation calls that replacement. 164 retained route/provider/auth/audit controls pass before and after. |
| Browser fixtures and tests | Users/overview fixtures import/patch shared reads/count and active provider methods; Users boundary/review/adversarial/audit tests import shared error/auth and active provider. These are test entry paths, not production callers of the legacy role helper. |
| `tools/verify_logical_pg_restore.py`, migration docs and operating-collection code | `supabase_admin` is a PostgreSQL role/ACL string, not a helper import. |
| Infrastructure/history documentation | Mentions shared role reads and prior acceptance; no additional executable helper caller. |

Retain the public helper. Repository absence cannot prove compatibility imports outside the repository are safe to remove, and the shared module is still imported by authentication and the active provider. A narrow transport/acknowledgment repair preserves the public function and error class without moving active Users routes or authentication.

The header guard protects the shared `_raw_request` choke point, so both direct REST reads and `_request` Auth Admin paths receive exactly one required apikey/Authorization. Per-call HTTPX `auth` is rejected because it overrides Authorization after merging; no inventoried caller uses it. Caller header names are collapsed case-insensitively (last supplied value), then required headers take precedence. Prefer is emitted once. No role vocabulary restriction or profile-column allowlist was introduced.
