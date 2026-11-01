# Coordinator acceptance addendum

All tests below use synthetic credentials and controlled storage/provider transports. Production activation is not authorized. The production-package Docker selections use the previously audited 81 runtime distributions plus a separate test overlay, actually executing Python 3.12.16, SQLAlchemy 2.0.55 and Pillow 13.0.0. Source and environments are mounted read-only. Disposable PostgreSQL runs in a namespace with no external networking and no published host port; every owned container is stopped after its selection.

| Selection | Normal | Optimized | Scope |
| --- | --- | --- | --- |
| Mounted API, social commands, actual PG domain/native-worker/role/queue/schedule/media locks and maintenance | 299 pass, zero skips | Same 299 plus three combined mounted-media/manual API cases: 302 pass, zero skips | Real queue/delivery code with intercepted providers; actual local SQL/migrations/roles/restart and race behavior. |
| Recorded media ownership plus full current migration-head integration | 36 pass, zero skips | 36 pass, zero skips | `test_media_owned_postgres.py`, `test_media_owned_review_postgres.py`, `test_b17_combined_media_schema.py`. |
| Media retirement protocol | 7 pass, zero skips | 7 pass, zero skips | `test_media_retirement_postgres.py`, actual migration chain and conditional writer/history guards. |
| Independent maintenance report | 2 pass, zero skips | 2 pass, zero skips | `test_media_operator_postgres.py`, real read-only PostgreSQL report and drift/snapshot controls. |
| Combined cold restore and mounted-media/manual API | 6 pass, zero skips | 6 pass, zero skips | Fresh logical reconstruction plus missing/corrupt-original controls; API acceptance remains queued and idempotent. Both reviewers also independently reran the normal selection. |

These selections overlap. They are not summed into an inflated total. Existing warnings concern test-client/SQLAlchemy/Alembic compatibility; no failure is suppressed. Optimized runs retain pytest's warning that application assertions are disabled, while pytest rewrites assertions in test modules.

## The 17 disclosed media skips

The broad exact-package media cohort retained 17 skipped cases. All were selected for additional execution:

- Eight cases require PostgreSQL. They passed in the normal and optimized assigned database selections above, with the original fixed database/port safety checks preserved.
- Nine require real ffmpeg/ffprobe. The existing host installations were used without downloading or installing anything. Selecting `test_media_inspection_adversary.py -k actual` executed **21 cases, zero skips, 115 deselected** in 4.88 seconds, including all nine skipped real-video cases. Valid H.264/AAC, corrupt packets and missing final-packet controls executed against ffmpeg/ffprobe 9.0.1. This is explicitly a host compatibility run using existing Python 3.14.0/Pillow 12.1.1/SQLAlchemy 2.0.46, **not** exact production-package or deployed-host video acceptance. A preliminary incorrect `-k native` selector selected zero cases; it is not counted as a passing run.

The existing scoped deployed ffprobe acceptance remains separate. Local absence of the binaries in the test image is not proof of a missing deployed binary, and host compatibility does not establish every property of the production video toolchain.

## Receipts and limits

The coordinator evidence directory `manual-publish-launch-20261101` under the existing admin-redesign evidence root contains `pg-result-summary.json`, the eight `*-pg-*.xml` receipts and logs, `owned-media-pg-receipts.json` with exact commands, `combined-manual-restore-normal.xml`, `combined-manual-restore-optimized.xml`, and `host-native-video.xml`. Source changes for this media PR are confined to the cold-restore fixture and documentation; runtime media code needed no fix from these executions.

These results do not establish an application PostgreSQL/R2 production restore, provider send, actual-host sustained workload, approved retention policy, independent custody, representative operating cost, or OAuth ingress privacy. The unmet gates in [LOCAL_ACCEPTANCE.md](LOCAL_ACCEPTANCE.md) remain open. No production storage object, database row, environment, account, worker or publishing control was changed.
