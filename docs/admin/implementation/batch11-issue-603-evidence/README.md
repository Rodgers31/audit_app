# #603 portable evidence

`history/ORIGINAL_RUNS.tar.gz` and `history/MANIFEST.json` preserve 213 original files and 31 JUnit inventories. SHA256 `adc51659677a2f48bd09f79ca75c9d98f143c4bba2b6fb2ea5745ed7ce2c337b` identifies the archive. Original failed, setup, interrupted, negative and successful bytes remain historical evidence. The manifest certifies archive integrity only; it cannot certify a later source. Empty setup inventories are explicitly classified, with no executed cases. `history/main-base.py.gz` and `inventory-base.json.gz` preserve the accepted financial source and pins; the dated review explains the narrow current pin update.

The first independent review executed all raw group controls (26 pass/1 stored-release failure per ORM) and nine startup modes per ORM, then its reporting turn was interrupted by a runtime filter. Its resource ledger confirms exact cleanup. Root preserved the failure and fixed it; later independent Spec execution passed the final30 cases. Standards review reproduced malformed timestamp/environment and portable invocation false acceptance; root preserved8 intended assertion failures, repaired validation and passed33 controls. No interrupted review is treated as final approval. Initial reports/raw packets are in the archive; final reports are external and bound by the final source binder.

Broad core execution is a failed prerequisite run:14446 passes,1427 skips,7 failures,202 setup errors. Six workflow cases lacked Node (later20/20 passed with the bundled read-only Node runtime); backup cases refused strict private-file permissions; reconciliation cases lacked their required explicit owned database. It also created an untracked seeding cache, making source_stable=false despite unchanged tracked hashes. The cache is retained externally. Legacy ETL passed295 with41 explicit financial-absence PostgreSQL skips. These are not passing whole-suite acceptance. Exact identities, diagnostics and all unchanged prerequisite skip reasons are in the manifest. The scoped repair cohort and legacy38 PostgreSQL controls execute separately on both ORMs with fresh final outputs.

Run from a checkout of the delivered branch with a compatible Python/pytest/SQLAlchemy runtime. Set an inert owned SQLite DATABASE_URL, inert JWT_SECRET_KEY and backend-only PYTHONPATH; disable dotenv. Never supply production credentials. Existing runtimes may be read-only. The automatic PostgreSQL fixture requires Docker and the pinned PostgreSQL17.11 arm64 image, reserved loopback55530 free; it owns/cleans exact container/network/volumes. No provider is used: actual CLI orchestration runs an inert barrier handler. Other lane reservations55531/55532/55534 are excluded. Historical compatibility uses explicitly verified55485; unchanged prior automatic fixtures use55492/55520. API18030 is unused.

Example portable invocation (replace placeholders with owned absolute paths):

```sh
env PATH='<runtime-bin>:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin' \
  DATABASE_URL='sqlite:///<owned-output>/inert-parent.sqlite' \
  JWT_SECRET_KEY='inert-bootstrap-key' PYTHON_DOTENV_DISABLED=1 \
  PYTHONPATH='<checkout>/backend' \
  <python> docs/admin/implementation/batch11-issue-603-evidence/publish.py \
  --root '<checkout>' --out '<fresh-external-output>' \
  tests/test_batch11_bootstrap_admission.py tests/test_batch11_bootstrap_evidence.py
<python> docs/admin/implementation/batch11-issue-603-evidence/verify.py \
  --root '<checkout>' --index '<fresh-external-output>/INDEX.json'
```

The publisher invokes the unchanged Batch10 recorder and actual `python -m pytest`, then publishes and reads back hashed raw output/JUnit/receipt. Complete unique case identities/counts, UTC timestamps/order, exact inert flags/redaction/presence metadata, runtime/entrypoint, portable correspondence, all consumed source hashes and before/after identity are verified. Current acceptance rejects historical source, internal/symlink output and malformed metadata under normal/optimized Python. `--history-only` proves packet integrity separately. Original raw execution commands retain their measured runtime paths; new `portable_command` expresses a rerunnable invocation without author runtime paths. Never rebind an old receipt to new source.

`legacy_replay.py --xml <fresh-external.xml>` creates the exact owned historical PostgreSQL prerequisite and executes all38 exclusion controls. `linux_replay.py --runtime-root <read-only-preinstalled-runtime-root> --out <fresh-external> [--minimum]` runs39 supplementary SQLite/lifecycle cases with read-only source/runtime mounts and network disabled. `full_replay.py --cohort backend|legacy --out <fresh-external>` uses the canonical complete core inventory/package ownership; it does not fabricate required reconciliation/backup prerequisites. `snapshot_history.py` publishes fresh immutable archive/manifest paths from existing histories, preserving bytes and explicit inventory classifications.

Fresh final packets/review reports and `POSTCOMMIT_BINDER.json` belong outside the checkout. The binder measures final remote HEAD/tree/tracked hashes and correspondence to final tested bytes after finished push, without chasing its own future hash in the committed handoff. Hosted acceptance and #583 production gates remain coordinator-owned.
