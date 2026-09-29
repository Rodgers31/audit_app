# Inflation 15→11 incident: recovery worksheet (#347)

The September 24 census job 3139 recorded 15 `inflation_rate` rows but no
identities. The September 28 census job 3171 recorded 11. The September 29
read-only diagnostic records the 11 surviving national year-end rows, IDs
26–35 and 98, all tied to World Bank source document 1856 and labelled CPI
inflation annual average. It records two removals by economic job 3160:
`2024-01-31 = 6.3` and `2025-01-31 = 3.3`. That old receipt omits row ID,
source ID, and coverage. Job 3180 removed nothing.

[PR #248](https://github.com/Rodgers31/audit_app/pull/248) describes a
September 26 production-derived clone whose live seed swept four off-cycle
tuples. The two additional tuples were `2023-06-30 = 7.9` and
`2024-06-30 = 4.6`. Those values and dates match the old bootstrap literals.
The clone result is independent evidence for the tuples; it does not identify
their live production IDs, stored source/measure, or deletion actor. The
bootstrap cleanup introduced through PR #326 could have removed them on a
backend start after its September 27 08:33 UTC merge, but there is no
row-level production cleanup receipt. This remains a hypothesis.

## Recover the missing identity and source evidence

If the **September 26 pre-change snapshot** from PR #248 is retained, restore
it into an isolated, read-only PostgreSQL instance. Otherwise use a
point-in-time restore before the PR #326 deployment. Record the snapshot
timestamp and content hash.
Run this query there. It reads only the public indicator records and their
source-document metadata. Save the complete 15-row result, not only the four
candidate tuples. Do not run a seed or bootstrap against this restore.

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '8s';
SHOW transaction_read_only;

SELECT e.id,
       e.indicator_type,
       e.indicator_date::date AS observation_date,
       e.value::text AS stored_value,
       e.unit,
       e.entity_id,
       e.source_document_id,
       e.metadata AS row_metadata,
       e.created_at,
       d.publisher,
       d.title AS source_title,
       d.url AS source_url,
       d.md5 AS source_md5,
       d.metadata AS source_metadata
FROM economic_indicators AS e
LEFT JOIN source_documents AS d ON d.id = e.source_document_id
WHERE e.indicator_type = 'inflation_rate'
ORDER BY e.id
LIMIT 40;

ROLLBACK;
```

Require exactly 15 rows in that output before comparing it to the current
11-row diagnostic. Match by **ID** and then inspect date, stored value,
entity, source ID, document publisher/URL, and any declared measure. A tuple
match alone cannot prove it is the same stored observation. Retain the full
before/after map and the four vanished rows as immutable evidence.

To identify the June deletion actor and timing, compare the same bounded query
on point-in-time restores immediately before and after the PR #326 Render
deployment, and before job 3160 at 2026-09-28 02:50 UTC. Correlate the
change with Render startup logs for `_seed_economic_indicators` and deployment
SHA; an absent log is not proof that the path did not run. A database audit log
or WAL-derived row deletion record would give stronger actor evidence. If
neither a pre-deletion snapshot nor retained row-level history exists, the
original IDs and source metadata are unrecoverable from the available
count-only censuses and old job receipts. Keep production diagnostics
read-only and serial under the coordinator.

## Decision rule

Classify each vanished ID separately. The two January rows have a live
old-format removal tuple; the June rows currently have only clone and code
evidence. Check the original row source and measure against the World Bank
annual-average series and the CBK 12-month series before calling a retirement
correct. If a source-backed annual observation disappeared, restore it through
an explicit reviewed correction. If all four were wrong-key off-cycle rows,
record the exact correction and source evidence; do not manufacture modern
identity receipts for old jobs. Keep the integrity gate's historical failure
visible until the incident is independently reconciled. A seven-day baseline
expiry is not closure.
