# Actual OAG trim and catch-up verification

Root operates this sequence in the accepted frozen writer window. Use the final
release checkout and private0700 operation directory. Privately supply the actual
approved target as `OAG_BOUNDARY_DATABASE_URL` and `OAG_ACCEPTANCE_DATABASE_URL`,
with verified TLS/CA inputs. No production capture or write ran in this session.
The immutable `ROUND20_SESSION_3_INPUTS.json` indexes the unchanged reviewed
eight PDFs, five execution entries and source/page hashes. Actual source IDs
come from the frozen database, not the dated packet or a locally allocated ID.

After the actual publisher/display-code corrections, capture the trim before
image from release root, then prepare the existing source-bound plan:

```sh
PYTHON_DOTENV_DISABLED=1 "$APPROVED_PYTHON" scripts/verification/oag_acceptance_images.py \
  --output "$PRIVATE_OPERATION_DIR/trim-before.json" capture --stage trim --operation "$OPERATION_ID"
PYTHON_DOTENV_DISABLED=1 "$APPROVED_PYTHON" scripts/verification/oag_boundary_correction.py \
  --pdf "$REVIEWED_OAG_PDF" --manifest backend/tests/fixtures/oag_boundary_reviewed_manifest.json \
  --output "$PRIVATE_OPERATION_DIR/trim-plan.json"
```

`REVIEWED_OAG_PDF` is retained FY2024/25 assemblies, SHA256
`aa72b0a512fe01ce8f40b9ed8597bd78657a9f441a8daf4963b07e661104d896`.
Review this freshly prepared canonical plan and its reported digest. Apply the
same boundary command with `--plan "$PRIVATE_OPERATION_DIR/trim-plan.json"
--expected-plan-sha256 "$REVIEWED_PLAN_SHA"`, first to a new default read-only
output, then with root-authorized `--commit` to a new durable recovery output.
The helper validates source text and refuses stale Entity metadata; do not reuse
the old pre-code plan. This required correction check is not another generic
eight-PDF extraction rehearsal.

Capture and compare the real after-state:

```sh
PYTHON_DOTENV_DISABLED=1 "$APPROVED_PYTHON" scripts/verification/oag_acceptance_images.py \
  --output "$PRIVATE_OPERATION_DIR/trim-after.json" capture --stage trim --operation "$OPERATION_ID"
PYTHON_DOTENV_DISABLED=1 "$APPROVED_PYTHON" scripts/verification/oag_acceptance_images.py \
  --output "$PRIVATE_OPERATION_DIR/trim-comparison.json" compare \
  --before "$PRIVATE_OPERATION_DIR/trim-before.json" --after "$PRIVATE_OPERATION_DIR/trim-after.json" \
  --plan "$PRIVATE_OPERATION_DIR/trim-plan.json" --expected-plan-sha256 "$REVIEWED_PLAN_SHA"
```

This permits only audit5545/5679/5716 finding text and extraction6023/6158/6196
finding-text JSON, plus their recomputed audit extraction-JSON hashes. Source2541
and every other source column stay unchanged. All579 other shared-source findings
and all unrelated audit/extraction/Entity/Country/FiscalPeriod columns and IDs are
protected by nonempty full-row/schema aggregates. The reviewed source pages are
168/221/239 (printed155/208/226). An intent receipt is not a committed after-image.

Capture the actual post-trim catch-up baseline, execute the already merged bounded
command from `backend`, then capture the real adoption and compare:

```sh
PYTHON_DOTENV_DISABLED=1 "$APPROVED_PYTHON" scripts/verification/oag_acceptance_images.py \
  --output "$PRIVATE_OPERATION_DIR/catchup-before.json" capture --stage catchup --operation "$OPERATION_ID"
# In the same release checkout's backend directory:
"$APPROVED_PYTHON" -m seeding.cli seed --domain audits \
  --audits-source-manifest ../docs/operations/2026-10-01-round11-oag-catchup/manifest.json \
  --audits-observe-listing --no-dry-run
# Return to the release root:
PYTHON_DOTENV_DISABLED=1 "$APPROVED_PYTHON" scripts/verification/oag_acceptance_images.py \
  --output "$PRIVATE_OPERATION_DIR/catchup-after.json" capture --stage catchup --operation "$OPERATION_ID" --coverage
PYTHON_DOTENV_DISABLED=1 "$APPROVED_PYTHON" scripts/verification/oag_acceptance_images.py \
  --output "$PRIVATE_OPERATION_DIR/catchup-comparison.json" compare \
  --before "$PRIVATE_OPERATION_DIR/catchup-before.json" --after "$PRIVATE_OPERATION_DIR/catchup-after.json" --require-coverage
PYTHONPATH="$APPROVED_RELEASE_CHECKOUT/backend" "$APPROVED_PYTHON" \
  "$ROUND20_BANK/ROUND20_SESSION_3_FULL_VALIDATION.py"
```

Capture verifies `READ ONLY REPEATABLE READ` and always rolls back, with15second
statement/2second lock limits. It transfers full-row aggregate hashes for all six
protected tables, schema, eight source identities and six trim target rows. It
does not download PDFs or create jobs. Post-catch-up `--coverage` also reads actual
retained bytes and adopted evidence for every edition through the existing verifier
and the actual coverage consumer. It requires376 distinct cells matching the actual
47 Kenyan counties, four reviewed years and both institutions. Protected catch-up
rows exclude only the five actual selected source IDs; national2392,
legacy2395/2396, HomaBay2391, current2539/2541/2542 and every unrelated row remain
covered. Hashes prove comparison under trusted operator capture, not authentication
against arbitrary rewritten receipts. SQL aggregates scan the protected tables on
the server; measure actual time/transfer rather than claiming a quota bound.

The dedicated FULL runner binds the final merged validation source hashes and
executes the complete `seed.yml` body, with only verified read-only transaction and
rollback added. Its syntax/equivalence are verified locally; actual production/full
restore execution remains pending. Preserve its full output and require zero
critical errors plus complete qualified county coverage, then S2's signed backend
generation/every-worker acknowledgement, exact frontend paths and changed API and
real rendered source/text evidence at unchanged deployment SHAs/processes. A
preservation comparison alone never closes either issue.
If S1's CPI/cleanup writes remain scheduled, retain this diagnostic validation and
run the dedicated FULL runner again after their actual after-state. An unrelated
validation failure does not erase a valid trim/preservation result; final refresh
and combined acceptance still require the successful complete validation.

The seed itself observes publisher HTML once within existing domain/1320second
total budgets, commits a job even on refusal and may commit earlier selected
volumes before timeout. No preparatory live publisher request ran here. If root
needs another HTML/PDF request to resolve an actual adoption failure, coordinate
one bounded purposeful observation before requesting it. A network/HTTP/MIME/
redirect refusal is an outage or unqualified response, not proof of a missing
edition; a successful parsed listing missing a reviewed edition is the distinct
inventory refusal. Retain the actual job discovery errors and completed page
receipts. Do not suppress either, download unselected PDFs, invent bindings or
automatically repeat a seed. Reconcile actual committed state before a reviewed
resume or recovery.

#379 can close once the exact three stored/extraction texts and579-row preservation
pass, and all three public API/rendered texts show their reviewed source/page links.
A publisher outage may leave#234 pending while this independently valid correction
proceeds. #234 closes only after actual five-edition adoption, complete eight-edition
coverage/provenance, dedicated FULL validation and actual refresh/public acceptance.
Actions remains OFF; root owns production operations and GitHub writes.
