# Legacy source checkers after issue #301

The unused `backend/main_simple.py` mock application and the financial mock
functions in `etl_test_runner.py`, `comprehensive_kenya_etl.py` and
`tools/alternative_sources.py` are retired. No financial replacement feed is
implemented by these scripts. Invented budgets, spending, execution rates,
county populations and audit claims are removed together with their mock records.

The retained Python CLIs check HTTP access and discover document links. They
return `financial_data: null` (or `comprehensive_data: null` in the combined
checker) and `financial_data_status: "not_extracted"`. Links are not downloaded
or authenticated financial observations. Empty entity lists and a zero download
count describe work performed by these checkers, never a zero budget or debt.
HTTP failure, timeout and parse failure are accounted for as failed source checks.
CLI exit 0 means the requested source checks succeeded; exit 1 means at least
one source check failed. No data completeness or financial quality score is
published. Each pipeline invocation reports a new batch of checks.

`demo_complete_system.sh` calls the retained simple checker, prints source/link
observations, and stops if that checker exits nonzero. It accepts an output path
as its first argument and an optional `PYTHON` interpreter override. The three
Python CLIs accept `--output`; their existing default output filenames remain.

## Caller and deployment boundary

- Repository entrypoint searches found no caller or configured launch of
  `backend/main_simple.py`. The backend Dockerfiles start `main:app`, with
  `backend/` as their build context.
- `comprehensive_kenya_etl.py` has its own CLI and is imported by
  `ultimate_kenya_etl.py`. The combined checker now imports the source probes
  from `tools.alternative_sources`; its old import targeted the empty root
  `alternative_sources.py` and failed. The combined checker retains source
  observations and explicitly absent financial data instead of mock generation.
- `etl_test_runner.py` has its own CLI and the shell demo caller. The shipping
  `/api/v1/etl/kenya/sources` route is a catalogue and does not invoke this script.
- `etl/Dockerfile` copies the whole tree and starts `etl.worker`, which calls
  `etl.backfill`. Those entrypoints do not invoke the retired generators.
  Image inclusion alone does not establish deployment reachability.
- JSON filenames also occur in organizer/diagnostic tools and the alternate
  data-driven analytics reader. Those references do not call these generators;
  this change does not modify historical JSON artifacts or authorize their use.

The reviewed literal inventory removes exactly 7 + 22 + 3 + 10 sites for these
four modules. All remaining entries and AST hashes are unchanged: 18 contextual
values and the five regional peer sites assigned to issue #424. This is a code
retirement, not evidence of 42 production incidents or repaired production data.
