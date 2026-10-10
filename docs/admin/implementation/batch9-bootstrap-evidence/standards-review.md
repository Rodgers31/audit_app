Independent Standards review, 2026-10-09. Compared the working tree with pinned
`9e97ca3f1ca43f103a8655447a86d889456a218a` using
`git diff 9e97ca3f1ca43f103a8655447a86d889456a218a -- backend/bootstrap.py`.
Read `CONTEXT.md`, `TESTING_GATES.md`, the Batch 8 exclusion contract/handoff,
the actual seam, and new bootstrap tests/fixture. No applicable AGENTS.md or
CLAUDE.md was found. Historical CI assertions were not treated as executed gates.

**One confirmed finding, repaired; no unresolved Standards finding.**

[P2] The first factory implementation converted a supplied SQLite Connection
to its Engine. Claim refusal then rolled back the caller's reused DBAPI
transaction, removing already seeded counties and leaving ORM identities
pointing at deleted rows. This violated the supplied-session requirement and
the state-persistence rule that failure must preserve the authoritative caller
state. Independent reproduction of the existing population writer
`bootstrap_slugs` test produced **1 failed**, `ObjectDeletedError`:
[`standards-session-red.txt`](standards-session-red.txt), with source hashes,
command and inert environment in the matching JSON receipt.

The fix at `backend/bootstrap.py:1034` preserves the SQLite bind and sets
`join_transaction_mode="create_savepoint"`. Independent ORM controls demonstrate
why bind preservation alone is insufficient: `conditional_savepoint` produced
`caller_effects=0, outer_active=false`; `create_savepoint` produced
`caller_effects=1, outer_active=true`. Both Python 3.13.9/SQLAlchemy 2.0.46 and
Python 3.12.15/SQLAlchemy 2.0.23 produced those results:
[`standards-session-control-current.txt`](standards-session-control-current.txt),
[`standards-session-control-min.txt`](standards-session-control-min.txt).
The control generator SHA256 is
`429708768a4979ac33587f63bd6cfa1a9709488008c5778382b2394582fed0a4`.

Replayed the existing regression plus all seven new session cases: **8 passed,
0 failed, 0 skipped** on each runtime, covering refusal preservation and coherent
versus invalid budget results:
[`standards-session-green.txt`](standards-session-green.txt),
[`standards-session-min-green.txt`](standards-session-min-green.txt).
The selections overlap; they establish eight distinct cases.

Final reviewed bootstrap SHA256:
`4d28994ffa3e1b8564e7969b2f105633f6e93a8f40fefe2c142ed5913570f12d`;
session tests:
`5ecd26ef09f304d05f37ef85de1281c778e7e4db172286fb3f7743e7d33254d5`.
Receipt generator `record.py` SHA256:
`9dae10f5f6e9f32342f421e0961d336066fa9044021ef9b7ad357981f3626201`.

The existing country/period helper commits remain unchanged
(`bootstrap.py:513,538`); county and budget mutations still precede the final
outer commit, and release delegates to the held seam. No additional concrete
smell or scope defect was found. These independent checks establish SQLite
session behavior, not PostgreSQL/process exclusion, hosted CI, deployment or
complete #582 acceptance. Product and test files were not edited by this reviewer.
