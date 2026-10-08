# Bounded backend job capacity

The complete native hosted cohort contains 11,074 selected cases. A 15-minute
whole-job deadline includes service startup, dependency installation, pinned
image preparation, collection, all tests, coverage and import verification.

Actual run [37174217684](https://github.com/Rodgers31/audit_app/actions/runs/37174217684)
reached 5,198 passes / 449 existing skips before the deadline. After the measured
lazy-schema and guard-traversal/tokenization repairs, actual run
[37175925618](https://github.com/Rodgers31/audit_app/actions/runs/37175925618)
reached 9,413 passes / 1,034 existing skips (10,447 results of 11,074 collected)
before the same deadline. Both were cancelled, not accepted as complete runs;
no failed/error test verdict was recorded. Coverage and API smoke did not run.

A further covered 133-case schema-introspection experiment measured 38.49s
before / 39.62s afterward, with only 0.29s setup saving. It was rejected and
restored. A broader schema-cache rewrite is not justified by that profile.

The backend job cap is therefore 20 minutes in both automatic CI and the
manual workflow. It is still finite, and all 11,074 cases remain selected with
the original assertions, skip requirements, `--maxfail=5`, coverage and API
smoke. This is a whole-job capacity correction, not a test-result waiver.
No request, media decoder, backup/restore watchdog or image-preparation timeout
is changed. Pinned image preparation retains its shared 240-second deadline
and five-minute step limit without retries. Manual frozen-SHA/event/scope/
attempt-one guards and full/manual job parity remain enforced.

Repository Actions stays off between expressly approved manual runs. During
backend-only verification the other jobs and full quality gate are explicitly
skipped; success is not described as full all-job acceptance. Turn Actions and
the manual workflow off immediately after the completed run. Automatic CI,
Docker and seed workflows remain disabled during this development phase.
