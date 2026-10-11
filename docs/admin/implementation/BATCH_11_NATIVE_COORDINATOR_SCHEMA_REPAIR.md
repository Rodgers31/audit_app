# Native coordinator fixture schema repair

Scope: #630, additive coordinator fixture integration for PR #626. Production
worker, native migration, capability, ownership and browser assertions are
unchanged.

The complete combined gate at `75bc69c04a45b7eceffe47ddbdd9c1c2ea2c3282`
([run 38087700192](https://github.com/Rodgers31/audit_app/actions/runs/38087700192))
recorded ten coordinator failures before acceptance: worker capability remained
unavailable. Preserved PostgreSQL observations record exited actual workers;
unexpected-transport attachments are empty. The separate public back/forward
scroll failure remains an independent investigation.

On source `18c847f6f26ca355cb9cd38a9472ebc1db591daa`, the unchanged fixture applies
only the four-source mapping. Actual worker registration enumerates every native
domain, including an unavailable CRA row with its opt-in disabled. An owned
loopback PostgreSQL reproduction executes the real worker CLI (exit 1,
sanitized `Dedicated worker unavailable.`). A separate call of the actual
registration function records `ck_etl_dispatch_domain` rejecting
`(cra, null, null, f)`. Both observations describe the same unchanged fixture;
the registration traceback is separate diagnostic evidence, not CLI output.

The fixture now inventories the exact native `e602b11a0001` alteration after the
previous mapping, before database access. Missing and unrelated replacements
refuse before I/O. PostgreSQL renders the expected CHECKs for comparison:
exactly validated previous four-domain constraints admit the actual native
migration; exactly current five-domain constraints require no alteration;
partial, absent, unrelated or NOT VALID constraints refuse. Ready-column shape
is validated before this decision. Final schema validation uses the actual
current model contracts. Existing quiescence and migration locking stay intact.

Preserved observed-red workflow controls record three failures: actual-model
inventory and missing/unrelated native refusal. The repaired nine controls pass
on current and supported-minimum SQLAlchemy, in normal and optimized Python
(36 independent executions). Reproduce the default workflow boundary suite with:

```sh
python -B .github/scripts/tests/test_coordinator_fixture_schema.py -v
python -B -O .github/scripts/tests/test_coordinator_fixture_schema.py -v
```

Actual owned PostgreSQL controls confirm repeat preparation of a valid current
fixture; refusal without committed repair for partial, missing and unvalidated
CHECKs and a wrong ready default; and real CLI readiness with `cra:false` while
opt-in remains disabled. Each negative compares database definitions before and
after refusal. Owned process group, container, network and volumes are removed.

Coordinator external evidence under `BATCH_11_REVIEW/` retains immutable
versioned drivers, complete raw outputs, explicit source hashes and cleanup:
`630_WORKFLOW_RED_V1`, `630_COORDINATOR_ACTUAL_RED_V3`,
`630_COORDINATOR_FINAL_WORKING_GREEN_V2`, and independent
`TOOLING_FIXES/630-fixture-independent-02`. Earlier setup/parser expectation
failures are retained separately and are not behavioral acceptance. Final
postcommit, supported-minimum worker and hosted integration evidence is added to
the coordinator review record and PR brief on its actual tested source.

The earlier 191-case-per-runtime CRA product proof remains bound to its original
source; this fixture-only repair does not reinterpret those original receipts.
The fresh complete gate must execute all original coordinator journeys on the
final combined source. #602 remains partially complete pending OpenData #621;
#583/#554 remain production rollout and operator-acceptance gates.
