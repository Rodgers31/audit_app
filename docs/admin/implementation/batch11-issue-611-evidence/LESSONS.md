# Proposed lessons for coordinator review

Shared skills were read only. No shared policy or skill was edited.

1. A boolean readiness row and dataset UUID copied by pg_dump/PITR cannot
   independently certify a restored xid8 transaction namespace. Require a
   separately accepted incarnation/restore authority before activating a durable
   visibility reader; record actual restored-history controls or explicit gaps.
2. Capability checks must validate effective RLS policy expressions as well as
   RLS enablement. The owned `ALTER POLICY ... USING(false)` control returned an
   incorrect empty 200 before the prototype repair; retained policy-red output
   and current/minimum replays demonstrate the gap and repair.
3. uvicorn can re-raise a caught shutdown signal after lifespan shutdown. Browser
   fixture cleanup in a Python `finally` after `uvicorn.run` did not execute in
   the first Playwright attempt. Moving cleanup into application lifespan still left two
   tables and three roles after a passing journey. The later fixture therefore
   invokes an explicit cleanup endpoint and checks zero tables/roles within the
   journey, then separately reads back database objects and ports after shutdown.
   Keep both earlier attempts as diagnostic evidence rather than accepting their
   resource lifecycle.
4. Minimum dependency acceptance needs a supported interpreter too. SQLAlchemy
   2.0.23's Python 3.13 import failure is setup evidence; an owned downloaded Python
   3.12 runtime provided the actual minimum-ORM behavioral replay. Do not patch
   the dependency's compatibility guard or call the import failure a product red.

5. A linked checkout guard must exclude the resolved common Git directory and
   every registered source checkout. Recheck destination identity after child
   execution. Verify testcase identities against raw JUnit, runtime against its
   captured probe output, and source/HEAD against the live checkout; a well-typed
   invented receipt is not execution evidence. Preserve original false passes
   and repair replays separately. Local hashes do not authenticate a party who
   can rewrite the entire packet; retain an external source/publication binder.
