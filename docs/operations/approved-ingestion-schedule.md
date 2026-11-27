# Scheduling ingestion on the approved release

GitHub starts scheduled workflows on the default branch. While a new revision
awaits deployment, that can differ from the revision approved to run production
ingestion. The existing gate refuses the difference before opening a writer
connection. Run 45927116809 is one example.

The approved release dispatcher uses the existing daily and weekly slots. It
reads `INGESTION_WRITE_APPROVED_SHA`, checks that the lightweight Git tag
`ingestion-release-<full SHA>` points directly to that commit, then dispatches
`seed.yml` on the tag. The dispatch summary links the writer run and confirms
its captured SHA. Read the linked writer run for database, validation, and signed
cache refresh results.

## First activation and subsequent releases

- Keep `INGESTION_APPROVED_TAG_SCHEDULE_ENABLED` unset until the first exact
  release containing both workflow changes has been approved and deployed.
  Verify the deployed Render revision and both Vercel domains under the existing
  acceptance procedure.
- Create and read back a lightweight `ingestion-release-<full SHA>` tag on the
  approved published commit. Used tags are immutable release references.
  Update the existing ingestion pin only after production verification, then
  enable `INGESTION_APPROVED_TAG_SCHEDULE_ENABLED` during a window without an
  active or imminent writer. `INGESTION_NIGHTLY_ENABLED` still controls the
  nightly schedule.
- Follow the first nightly dispatch through database admission, actual writer
  execution, integrity validation and both signed refresh calls. Check the
  `github-actions[bot]` actor, the requested tag and the exact captured SHA.
  A successful dispatch confirms capture only.
- Future releases follow the same provider, tag and pin verification. The
  previously verified tag and pin continue to define the admitted release
  while changes accumulate on `main`. Caches saved under a different release
  tag are out of scope for a new tag, so verify cold-run source availability.

A missing tag, changed pin, wrong SHA, wrong workflow or unauthorized tag actor
stops the affected path before writes. The scheduled child uses the same
production concurrency group, schema qualification, parser admission, daily
and weekly domain selection, and signed refresh eligibility as the legacy
nightly. Manual dispatch from exact approved `main` remains available.

To revert the dispatcher, set `INGESTION_APPROVED_TAG_SCHEDULE_ENABLED` to
`false` during a quiet window. The legacy schedule resumes from `main` and
requires `main` to match the deployed and separately approved ingestion SHA.
