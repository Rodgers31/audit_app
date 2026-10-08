# PR #515 admission review receipt

Review target: `e02ba27`, native adapters stacked on the inspected media work.
The concrete [review thread](https://github.com/Rodgers31/audit_app/pull/515#discussion_r4221411448)
identified the synthetic eligible capability used at the adapter HTTP boundary.
The finding is partly correct: existing worker repository checks already reject
persisted eligibility, adapter, publishing, price, limits, required scopes, rules
and format restrictions before creating an intent. Injecting the registry alone
does not bypass those checks. Two additional persisted fields, provider API
version and granted scopes, were not compared there. An account capability
change after intent commit also reached the adapter without a current admission
proof. Direct adapter calls ignored all persisted publishing restrictions.

## Fix contract

`NativeCapabilityAdmission` contains only immutable admission fields, including
strict booleans, scopes, ordered limits, publishing state and price. It contains
no credentials, provider response or private URL. The credential loader extracts
this proof from the locked current account after intent creation; malformed or
missing state becomes no proof. Every raw admission field, including publishing
state, must be explicitly present before schema defaults can be applied. Fake
adapter fixtures must explicitly supply a
verified proof to authorize a mutation.

One comparison now serves API validation, the explicit native worker mutation
hook and the adapter's final material check. Persisted and current API version,
rules, formats, required/granted scopes and limits must agree, with eligibility,
adapter availability, supported publishing and free price required. The payload
rules version must also match. Every native mutating step uses the hook before
intent creation, including a target already in processing, and verifies the
loader-carried proof before HTTP. Existing explicit fake adapters without the
hook retain their protocol. Default registration remains off.

Publishing restriction does not erase an accepted send. Authenticated poll and
reconciliation retain credential identity, expiry, immutable payload, checkpoint
and ownership checks while permitting reads under restricted or malformed
publishing admission. This change supplies no mutation retry or provider-complete
absence proof. The locked material snapshot is the admission point; no claim is
made that an account row remains locked during the network call.

## Executed baseline and repair

Before changing product code, the new SQLite loader/provider cases produced
**11 failures and 2 passing positive/recovery cases**. Each of the 11 restricted
materials still issued a publishing POST. The initial random-schema PostgreSQL
cases produced **13 failures and 9 passes**: stale API version and granted scopes
each dispatched before intent admission; all 11 changes injected immediately
after committed intent still dispatched. The valid baseline and eight existing
repository restrictions passed. Those passing restrictions support the partial
verdict above rather than the review's broader registry-bypass claim.

After repair, direct loader tests also cover authenticated poll/reconciliation
under all 11 restrictions. Actual PostgreSQL readback preserves a known Facebook
send after the stored capability becomes malformed: one publishing POST, one
verification GET, public success and no resend. An actual Instagram flow reaches
the processing `publish_ready` checkpoint with four recorded operations. Its
valid baseline publishes; stale API version or stored granted scopes blocks the
next publish without a fifth intent or additional HTTP. The PostgreSQL admission
file passes **26 tests**.

Independent review then found a missing-field normalization case. A stored
snapshot without `rules_version` inherited the current schema default. The
retained loader/adapter regression was observed red with confirmed publishing
success, then green after requiring raw admission fields. All 11 missing-field
cases now produce no proof and no HTTP; omitted source links and verification
timestamp remain accepted because they are outside the admission contract.
The complete bounded repair command below passes **257 tests**, with one
pre-existing SQLAlchemy declarative-base deprecation warning.

An independent reviewer executed **57 cases**: 35 retained loader/provider tests
and 22 separate probes. These covered missing fields at extractor, predicate and
API boundaries, optional metadata, absent/raw proofs, forged read-only mutation
plans, restricted Facebook photo publication, and PostgreSQL changes before and
after intent creation. Owned reads and lost-receipt recovery preserved the
original intent without resending. An earlier independent run of 50 loader,
PostgreSQL and credential-rotation cases also passed. No additional finding
remained after the missing-field repair.

The bounded repair command is run from `backend`, using the configured Python
environment, fake provider HTTP and the dedicated random-schema domain database:

```sh
SOCIAL_TEST_DATABASE_URL=postgresql://postgres:social_local_test@127.0.0.1:62124/social_domain_test \
PYTHONPATH=. python -B -m pytest \
  --confcutdir=tests/social -p no:cacheprovider -q --tb=short \
  tests/social/test_native_capability_admission.py \
  tests/social/test_native_capability_admission_postgres.py \
  tests/social/test_native_meta_adapters.py \
  tests/social/test_native_credential_race_postgres.py \
  tests/social/test_worker_materials.py \
  tests/social/test_worker_materials_adversary.py \
  tests/social/test_native_shared_attack.py \
  tests/social/test_native_shared_review.py
```

No live provider or storage request, deployment, production database, default
registry, runtime setting or dependency changed. The review body's additional
timestamp, media metadata, schema and interface claims had no concrete supporting
location or reproduction; this receipt does not invent findings for them.

Root merged media prerequisite `8d0a9d6` into the native branch and ran its full
backend social suite with all four explicit local PostgreSQL lanes enabled:
**1,089 passed, zero skipped**. The only two warnings were the existing
SQLAlchemy declarative-base deprecations. Worker tests ran serially against the
disposable database. The native PR diff still contains only native changes
relative to the updated media base; the migration graph retains its single head.
