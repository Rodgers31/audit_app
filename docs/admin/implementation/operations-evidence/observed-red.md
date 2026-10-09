# Observed red excerpts

These are excerpts of executed local command output, not inferred failures.
Exact commands and tested revisions are in the adjacent handoff.

## backend-red

```text
FAILED backend/tests/test_admin_operations_lane.py::test_unaccepted_trigger_never_inserts_or_records_success[False]
FAILED backend/tests/test_admin_operations_lane.py::test_unaccepted_trigger_never_inserts_or_records_success[True]
FAILED backend/tests/test_admin_operations_lane.py::test_health_does_not_certify_worker_from_calendar_calculation
FAILED backend/tests/test_admin_operations_lane.py::test_schedule_decision_contract_and_summary_are_plan_only
FAILED backend/tests/test_admin_operations_lane.py::test_planner_failure_is_safe_and_never_healthy[exception]
FAILED backend/tests/test_admin_operations_lane.py::test_planner_failure_is_safe_and_never_healthy[empty]
FAILED backend/tests/test_admin_operations_lane.py::test_planner_failure_is_safe_and_never_healthy[malformed]
FAILED backend/tests/test_admin_operations_lane.py::test_ingestion_query_bounds[ingestion-jobs?days=-1]
FAILED backend/tests/test_admin_operations_lane.py::test_ingestion_query_bounds[ingestion-jobs?days=0]
FAILED backend/tests/test_admin_operations_lane.py::test_ingestion_query_bounds[ingestion-jobs?days=366]
FAILED backend/tests/test_admin_operations_lane.py::test_ingestion_query_bounds[ingestion-jobs?days=99999999999999999999]
FAILED backend/tests/test_admin_operations_lane.py::test_ingestion_query_bounds[ingestion-jobs?page=10001]
FAILED backend/tests/test_admin_operations_lane.py::test_ingestion_query_bounds[ingestion-jobs?domain=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx]
FAILED backend/tests/test_admin_operations_lane.py::test_ingestion_query_bounds[ingestion-jobs/stats/summary?days=-1]
FAILED backend/tests/test_admin_operations_lane.py::test_ingestion_query_bounds[ingestion-jobs/0]
FAILED backend/tests/test_admin_operations_lane.py::test_ingestion_query_bounds[ingestion-jobs/2147483648]
FAILED backend/tests/test_admin_operations_lane.py::test_ingestion_projection_withholds_raw_diagnostics_and_tie_order_is_stable
FAILED backend/tests/test_admin_operations_lane.py::test_trigger_rejects_malformed_commands[payload0]
FAILED backend/tests/test_admin_operations_lane.py::test_trigger_rejects_malformed_commands[payload1]
FAILED backend/tests/test_admin_operations_lane.py::test_trigger_rejects_malformed_commands[payload3]
20 failed, 12 passed, 2 warnings in 0.84s
```

## ui-red

```text
  ✕ hostile URL parameters never reach the API and are replaced with bounded defaults (62 ms)
  ✕ filter labels are usable and filter changes use navigable history (1011 ms)
  ✕ an empty later page retains a way back to earlier jobs (69 ms)
  ✕ malformed lists are an error state, never no jobs or a table (1009 ms)
  ✕ malformed lists are an error state, never no jobs or a table (1013 ms)
  ✕ malformed lists are an error state, never no jobs or a table (1010 ms)
  ✕ malformed lists are an error state, never no jobs or a table (1006 ms)
  ✕ malformed lists are an error state, never no jobs or a table (1010 ms)
  ✕ desktop jobs have keyboard-accessible detail links and dry-run remains visible (1014 ms)
  ✕ a failed refresh stops showing old successful counts (31 ms)
  ✕ running jobs poll while visible, pause hidden and stop at completion (11 ms)
  ✕ calendar planning never renders running or healthy worker claims and unavailable controls cannot dispatch (10 ms)
  ✕ malformed schedule and health are recoverable errors (1007 ms)
  ● hostile URL parameters never reach the API and are replaced with bounded defaults
  ● filter labels are usable and filter changes use navigable history
  ● an empty later page retains a way back to earlier jobs
  ● malformed lists are an error state, never no jobs or a table
  ● malformed lists are an error state, never no jobs or a table
  ● malformed lists are an error state, never no jobs or a table
  ● malformed lists are an error state, never no jobs or a table
  ● malformed lists are an error state, never no jobs or a table
  ● malformed lists are an error state, never no jobs or a table
  ● desktop jobs have keyboard-accessible detail links and dry-run remains visible
  ● a failed refresh stops showing old successful counts
  ● running jobs poll while visible, pause hidden and stop at completion
  ● calendar planning never renders running or healthy worker claims and unavailable controls cannot dispatch
  ● malformed schedule and health are recoverable errors
  ● malformed schedule and health are recoverable errors
Test Suites: 1 failed, 1 total
Tests:       13 failed, 13 total
Time:        8.69 s
Ran all test suites matching /__tests__\/admin\/operations\/operations-ui.test.tsx/i.
```

## import-red

```text
FAILED backend/tests/test_admin_operations_lane.py::test_fresh_backend_import_resolves_the_calendar_without_shadowing_packages
1 failed, 32 deselected, 2 warnings in 0.41s
```

## state-red

```text
FAILED backend/tests/test_admin_operations_lane.py::test_negative_stored_counters_are_unavailable_not_success[items_processed]
FAILED backend/tests/test_admin_operations_lane.py::test_negative_stored_counters_are_unavailable_not_success[items_created]
FAILED backend/tests/test_admin_operations_lane.py::test_negative_stored_counters_are_unavailable_not_success[items_updated]
FAILED backend/tests/test_admin_operations_lane.py::test_reversed_recorded_timestamps_withhold_duration_instead_of_inventing_zero
4 failed, 33 deselected, 2 warnings in 0.17s
```

## initial-read-red

```text
  ✕ an initially hidden ingestion page awaits its first read without claiming empty or failed results (22 ms)
  ✕ an initially hidden etl page awaits its first read without claiming empty or failed results (9 ms)
  ● an initially hidden ingestion page awaits its first read without claiming empty or failed results
  ● an initially hidden etl page awaits its first read without claiming empty or failed results
Test Suites: 1 failed, 1 total
Tests:       2 failed, 13 skipped, 15 total
Time:        0.328 s, estimated 1 s
Ran all test suites matching /__tests__\/admin\/operations\/operations-ui.test.tsx/i with tests matching "initially hidden".
```
