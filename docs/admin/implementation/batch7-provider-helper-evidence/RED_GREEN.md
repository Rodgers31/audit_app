# Executed red/green receipts

All product executions used Python 3.13.9 from the read-only primary venv, a clean environment, owned absolute backend PYTHONPATH, `PYTHON_DOTENV_DISABLED=1`, synthetic credentials/identities and `.invalid` URLs. `httpx.MockTransport` executed the public helpers; neither `_raw_request` nor header construction was mocked. SQLite isolates import smoke checks (the existing provider import smoke also attempts a failed local audit write); no PostgreSQL lease/audit/JSONB semantics are certified.

Common runner command (executed from owned `backend/`):

```sh
python -m pytest --confcutdir=tests -q tests/test_batch7_supabase_helpers.py
```

| Phase | Actual outcome |
| --- | --- |
| Pinned old helper, initial public role/count regression | `1 failed, 2 passed in 0.05s`; role TypeError before HTTP transport, `requests=[]`; both actual count calls return 3. |
| Pinned active Users baseline | `164 passed, 2 warnings in 2.35s`. |
| Header repair only, initial same regression | `3 passed in 0.04s`. |
| Header repair only, acknowledgment matrix before response validation | `22 failed, 12 passed in 0.12s`; wrong id/roles/shape/multiple rows and redirects could return success; malformed/absent representation errors were incorrect. |
| Matching-row validation | `34 passed in 0.05s`. |
| Before explicit failure-verdict guard | `8 failed, 34 deselected in 0.07s`; matching fields with `ok/success` false/0/string or `error/error_code` did not raise. |
| Before HTTPX auth override guard | `1 failed, 65 deselected in 0.07s`; direct `auth=("caller","inert")` did not raise. Independent transport capture showed replaced Authorization. |
| After HTTPX auth override guard | `1 passed, 65 deselected in 0.05s`; static 400 before transport. |
| Final combined helper + fresh imports + retained Users controls | `232 passed, 2 warnings in 3.18s` (68 new helper/import cases + 164 retained controls). |
| Default pytest collection of new tests (without confcutdir) | `68 passed, 2 warnings in 0.81s`; no special marker excludes the regressions. Product lifespan was not entered. |

Pinned red traceback:

```text
memory = namespace(requests=[], response=<Response [200 OK]>)
supabase_admin.py:85:
    resp = client.request(method, url, headers=_headers(), **kwargs)
TypeError: httpx._client.Client.request() got multiple values for keyword argument 'headers'
1 failed, 2 passed in 0.05s
```

Final combined command:

```sh
python -m pytest --confcutdir=tests -q \
  tests/test_batch7_supabase_helpers.py tests/test_batch7_supabase_helpers_imports.py \
  tests/test_admin_users_boundaries.py tests/test_admin_users_review.py \
  tests/test_admin_users_adversarial_replay.py tests/test_admin_users_audit_policy.py
```

The two warnings are the pre-existing SQLAlchemy `declarative_base()` deprecations in database/models. Fresh package/top-level subprocesses block socket.connect and execute four real memory calls each: legacy role mutation/count, signed-token profile lookup and active Users role mutation.

Scoped critical lint (owned separate flake8 7.3.0 venv):

```sh
python -m flake8 supabase_admin.py tests/test_batch7_supabase_helpers.py \
  tests/test_batch7_supabase_helpers_imports.py \
  --count --select=E9,F63,F7,F82 --show-source --statistics
```

Actual output `0`, exit 0. The shared product venv lacked flake8; it was not modified. Full-backend critical lint instead exits 1 with unchanged `scripts/r2_producer_acceptance.py:440:9 F821 undefined name 'captured'`, also reproduced on the exact pinned file. #569 records this tooling-gate failure; no runtime PDF failure is claimed. A minimal closure/deletion runtime control passes, and the complete PDF producer remains unexecuted.

`git diff --check` passes. A bounded staged-diff private-key/JWT/service-secret/cloud-key pattern scan found no candidates; fixture values were manually checked as inert. This is not a repository-wide secret audit.
