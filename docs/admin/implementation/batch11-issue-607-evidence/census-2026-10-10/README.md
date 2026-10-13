# Complete issue and PR census addendum

The preserved author collector retrieved only the first page of each search.
An offline replay of its unchanged bytes returned a declared total of 134 but
retained only 100 records and issued no page 2 request. The earlier all-state
raw census remains intact; this finding concerns its missing complete producer
and the retained search collector, not an invented change to those old counts.

The new portable `tools/collect_issue_census.py` executed read-only GitHub
requests from 2026-10-10 20:20:21 through 20:22:12 UTC. It captured seven REST
pages containing 626 issue/PR rows, excluded 314 PR rows and retained 312
repository issues: 19 open and 293 closed. It fetched through a short terminal
REST page, refused duplicates/malformed records, reconciled search totals and
read all discussion/review/inline-comment pages for matched PRs.

| Search, scoped to Rodgers31/audit_app | Results | Page sizes |
| --- | ---: | --- |
| `"has exactly one h1"` | 1 | 1 |
| `"normal 47-county list"` | 1 | 1 |
| `is:issue counties in:title,body,comments` | 75 | 75 |
| `is:pr counties in:title,body,comments` | 122 | 100, 22 |
| `is:issue budget in:title,body,comments` | 95 | 95 |
| `is:pr budget in:title,body,comments` | 137 | 100, 37 |

The unions contain 126 relevant issue bodies with 341 discussion comments and
167 PR bodies with 263 discussion comments, 200 review bodies and 325 inline
comments. All 1,102 raw responses are retained, compressed without changing
their JSON bytes. Requests, query/page arguments, timestamps, exits and raw /
compressed hashes appear in the archive's `INDEX.json`. `details.json.gz`
contains the complete fetched bodies and comments. The publication manifest
binds all 1,104 archive members; the verifier reconstructs the census from raw
responses rather than trusting self-consistent summary counts.

Deduplication dispositions after reading the actual bodies and comments:

- [#607](https://github.com/Rodgers31/audit_app/issues/607) already tracks the
  pagination URL/table disagreement. The bounded repair addresses the pending
  response boundary; the naturally delivered-200 cause and full browser gate
  remain unresolved.
- [#601](https://github.com/Rodgers31/audit_app/issues/601) already tracks the
  saved-position scroll failure. This PR changes no scroll implementation and
  supplies no new natural-cause repair.
- [#622](https://github.com/Rodgers31/audit_app/issues/622) already tracks the
  budget FY2024/25 heading failure. Its cause/regression status remains open.
- [#623](https://github.com/Rodgers31/audit_app/issues/623) already tracks both
  original county initial-render signatures: zero immediate h1 and duplicate
  row-count visibility locator. They remain observations with no asserted
  shared cause.

No duplicate issue, comment, review, workflow or repository-setting mutation
was made by this collector. No financial, publisher or production database
operation occurred.

The original packet-v1/v2 files, historical producer scripts, failed browser
reports and receipts retain their exact bytes. Current author browser
acceptance remains **false**: 316 passes, 2 unexpected failures and 11 unchanged
fixmes across 329 cases, zero retries/flaky. This read-only census does not run
Chromium or satisfy that gate. A later coordinator acceptance must name its
own exact integration source, complete untouched original inventory and
hosted/local limits; it must preserve these earlier failures.

The census measured source at head `26a328ad5b69f0df2efbdefad7de1c0209744ffd`,
tree `be3aaba027efd2cf93203195a15ad6b273e78f57`, with the new collector supplied
as a separately hashed untracked producer. All existing tracked hashes were
unchanged during capture. Additive publication files are not attributed to that
earlier whole-checkout identity. The postcommit binder is recorded separately
after publication, avoiding a future-commit self-hash claim.

Ten unique offline collector tests passed, including the exact retained
first-page producer gap and second-page, exact-full-page, duplicate, malformed,
empty and output-ancestor controls. Their actual log/JUnit/receipt are retained
here as `offline-*`. Four additional actual-packet verifier tests cover positive
readback, a recatalogued omitted search page, self-consistent summaries that
disagree with raw issue rows, and an empty census. Fresh combined execution
receipts are in the coordinator review artifact directory.

Independent review then demonstrated that a recatalogued packet could omit
required searches or all selected full details while keeping its remaining
hashes internally consistent. The current verifier enforces the exact six
queries and repository, recomputes the complete selected issue/PR union,
and refuses missing details. Its ordinary CLI disables helper bytecode before
importing the collector so readback does not write into the source directory.
Seven regression controls supplement the original fourteen cases; all 21
unique cases passed with zero failures, errors or skips. Independent replay
reproduced the old omissions and confirmed their refusal after repair. These
verifier corrections preserve the actual captured producer and archive bytes;
they do not retag a new collection or upgrade browser acceptance.

Further independent controls showed that recatalogued source identities could
be replaced with nonexistent commits, an empty source map or an external
producer path. The current verifier now binds manifest/index identities,
requires the known relative producer with no linked ancestor, validates a
nonempty relative source map and checks that the captured Git commit resolves
to its declared tree. This requires the original captured Git object locally;
an unavailable object is a visible refusal. It does not assert that dirty
measured source equals a committed tree. Six additional controls bring the
actual complete offline inventory to 27 passes, zero failures, errors or skips;
before/after source hashes match and the owned process group is absent.
Independent final replay accepted the immutable original and refused the
coherently recatalogued invalid identities and omitted search.

To read the published packet without contacting GitHub:

```sh
python3 "$CHECKOUT/docs/admin/implementation/batch11-issue-607-evidence/tools/verify_issue_census.py" \
  --checkout "$CHECKOUT" \
  --archive "$CHECKOUT/docs/admin/implementation/batch11-issue-607-evidence/census-2026-10-10/census-v1.zip" \
  --manifest "$CHECKOUT/docs/admin/implementation/batch11-issue-607-evidence/census-2026-10-10/MANIFEST.json"
```

To capture a new census, invoke `tools/collect_issue_census.py --checkout
"$CHECKOUT" --output "$FRESH_EXTERNAL_DIRECTORY"`. Preserve old captures.
The output must be a fresh external directory with no symlinked ancestor.
The GitHub CLI uses its existing local authentication; no credential values are
recorded or forwarded into provider/build processes.
