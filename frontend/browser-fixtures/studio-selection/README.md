# Studio older-selection fixture

From `frontend`, run Node22 with the exact package lock installed and tooling repairs applied:

```
STUDIO_722_OUTPUT=/Users/roger/.codex/visualizations/<owned-evidence-directory> node browser-fixtures/studio-selection/serve.mjs
```

The server binds only127.0.0.1:33522. It uses the actual Studio, query library, Axios and response decoders; only Supabase session acquisition is aliased to an inert local module. HTTP fixtures contain21 source summaries and21 inspected assets. No provider, bucket, credential, upload or publishing endpoint exists.

Use your own existing Chrome tab. `/red` imports Studio from pinned baseline5189675; it has no next-source control and cannot reach the21st source. `/` imports the candidate. Choose Next source posts → Older eligible source → Existing older render → Next asset page → inspected-21.png → Add approved derivative to source draft. Page buttons and attach accept Enter. `http.jsonl` retains the bounded GET pages and actual attach request with expected_version7 and exact asset UUID. The returned revision advances; the fixture refuses repeated stale attachment. Wrong version/asset or missing key returns409.

Retain Chrome screenshots and DOM observations in the owned evidence directory. The fixture proves real component/client/HTTP integration, not backend database concurrency or production acceptance. Existing backend Studio tests cover the actual unchanged attach implementation. Stop the owned process on completion; no deployment route is added.
