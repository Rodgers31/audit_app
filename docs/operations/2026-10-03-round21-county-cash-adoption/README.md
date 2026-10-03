# Round 21 county cash adoption proposal (#299)

This packet is a local proposal. Production still has 37 supported county cash
sets; the six newly supported sets have not been adopted by this tool.

## Exact source and delta

The source is the original 935-page CoB annual FY2025/26 PDF, SHA-256
`5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3`.
The complete actual producer replay emitted 468 records. Its reviewed canonical
records and coverage SHA-256 is
`d3570dd4d3bf51a5662e19ab952224092820223da0d333ae3056eae2781c112b`.
The compiler refuses another producer output or a changed producer implementation.
It replays the existing county writer against an isolated full current cohort.

| County | Added cash total (KES) | PDF pages |
| --- | ---: | --- |
| Bungoma | 16,154,951,221.00 | 94–96 |
| Busia | 9,897,383,793.00 | 112–113 |
| Kilifi | 17,118,563,037.00 | 312–314 |
| Kisii | 16,499,037,626.00 | 330–332 |
| Kisumu | 13,360,566,017.46 | 349–351 |
| Kitui | 13,809,805,963.00 | 367–369 |

The delta is 40 new Revenue Receipts stream/Total rows and six provenance-only
updates on existing budget Total rows. The whole producer agrees with all
current source 2544 financial values, hashes, page references and notes.
The 37 accepted cash sets, four withheld counties (Kwale, Migori, Nyeri, Samburu),
all 47 summary OSR measures, all 47 full Entity images including current projects,
Source 2544 and period 9 are preserved. Source timestamp refreshes from the broad
writer are excluded from this scoped delta. No source conflict is resolved here.

## Guard and inverse

The compiler consumes explicit current whole capture, budget column/constraint
and sequence catalogue, eight internal FK trigger records, and the current
protected 15 table count/SHA capture. SQL checks every protected table using the
root's PostgreSQL typed-row length-framed SHA-256 algorithm. Budget after-images
are projected and hashed from the guarded current table before DML. Recovery
projects the original whole budget table and requires its retained SHA before
removing inserted rows. Period 9 and historical job 3157 are checked before and
after DML; new custom BudgetLine triggers are refused before executing them.

Both SQL files end in ROLLBACK and use explicit IDs. They issue neither nextval
nor setval. Under the supplied catalogue, IDs 4870–4909 are proposed. An authorized
commit must advance the owned sequence past 4909 while coordinated writer locks
remain held, with a durable before/after intent and receipt. Recovery retains a
known monotonic sequence advance and refuses unexpected sequence state; it does
not reset a sequence. Default rollback must leave data and the sequence unchanged.

The15 protected hashes are current inputs, not reusable assertions. Prior OAG or
source-disposition operations change their affected hashes. County identity must be COUNTY/country1 with the expected canonical slug; period9
must retain exact FY2025/26 bounds. All existing IDs and route metadata are retained.

Root must retain the
exact prior operation receipts and acquire a new reviewed capture, then regenerate
and re-review this cash packet before adoption. Do not silently remove a guard.

## Local verification receipts

The evidence bank is
`/Users/roger/.codex/visualizations/2026/09/27/01a0e1cf-a369-7b83-9e83-8d7900666170`.

- `ROUND21_CASH_PRODUCER_REPLAY.json`: full actual PDF producer (118.5s successful replay).
- `ROUND21_CASH_ADOPTION_IDENTITY_FINAL_PLAN.json` and `.adopt.sql` / `.recover.sql`: protected proposal.
- `ROUND21_CASH_ADOPTION_IDENTITY_FINAL_PG.json` and standalone `_PG.py`: 48 real owned
  PostgreSQL17 controls, including all 15 protected-table drifts, exact inverse,
  nullable period/job guards, new dependencies and hostile trigger/sequence controls.
- `ROUND21_CASH_PUBLIC_REPLAY.json`: actual public helper execution; all 47 captured
  baseline blocks equal the safe live response, local 37→43, 41 blocks unchanged,
  all 47 summary OSR measures unchanged, six hostile altered cash totals refused.
- `ROUND21_CASH_ADOPTION_IDENTITY_FINAL_CLI.json` and its SQL files: final CLI execution from the
  actual PDF; plan content equals the tested plan and SQL bytes match exactly.
- `tools/tests/test_county_cash_adoption.py`: 37 focused compiler controls.
  The existing county fetcher suite also passed 11 tests after sharing its mapper.

`ROUND21_CASH_ADOPTION_IDENTITY_BEFORE.json` retains four independently reported
compiler false greens before the identity repair. Six identity regression controls
now refuse the malformed captures alongside a healthy control.

Initial receipt serialization and isolated fixture setup failures remain in their
original logs. They were repaired before a PASS receipt was produced.

## Production acceptance remains pending

Root owns fresh reviewed production capture/rebase, current full backup plus
isolated restore, writer coordination and sequence advancement, the authorized
adoption transaction and receipt, then live public acceptance showing exactly 43
cash counties while 37 accepted sets and all four withheld states remain correct.
This local packet alone does not close #299.
