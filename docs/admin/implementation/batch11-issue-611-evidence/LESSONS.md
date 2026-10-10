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

6. A syntactically valid snapshot is not an issued bookmark. Authenticate the
   full visibility state, capture and ceiling together with scope and principal;
   test an actual lower-ID writer committed after capture and tamper one field
   at a time. Capability admission must include inherited table and column INSERT
   authority. Keep bounded prototype keys separate from durable production
   incarnation authority, and verify invalidation explicitly.
7. Preserve archived producer bytes when repairing provenance tools. Version
   the new producer/verifier, reject inventoried source links before hashing,
   and freshly replay instead of rewriting past receipts. Enforce advertised
   output freshness before launching browser servers or reporters.
8. A successful parent exit does not imply its descendants stopped. Scope all
   cleanup signals to the process group the recorder launched, include normal
   completion, escalate boundedly for resistant children and record actual group
   absence before acceptance. Test a detached harmless delayed effect as well
   as timeout. Fresh browser outputs also need an explicit same-run identity
   because Playwright workers reload configuration after output creation.
9. A zero child exit and markerless JUnit testcase can hide a nonstrict XPASS.
   Retain verbose pytest stdout and independently reconcile unexpected-pass
   status and summary evidence in both producer and reader. Exercise actual
   pytest-generated XML/output, color and interleaved prints, plus a passing
   parameter named XPASS and a recatalogued false-PASS receipt under normal
   and optimized Python. Local packet consistency is still not authentication
   against a party able to rewrite all raw outputs.
10. Physical cleanup and completed test work are different observations. An
    exited passing parent with a live child must be cleaned, but cannot certify
    completion afterward. Preserve survived-parent detection as refusal in
    both recorder and reader, even when the group is physically absent. Test
    the actual pytest parent and a coherently altered PASS verdict, alongside
    a normal no-survivor acceptance control.
11. A separately configured owned browser fixture still joins the normal suite
    if its spec is under that suite's testDir. Prove discovery with the real
    canonical list, place dedicated fixtures outside that directory, and run
    their standalone configuration separately. Keep the original canonical
    config/workflow and assertions unchanged; retain pre-move inventories and
    prove both ordinary exclusion and actual owned journey after relocation.
12. A directory move can escape one runner and enter another runner's broad
    filename match. Check each configured runner's real discovery inventory,
    make the smallest explicit partition change, and prove the exact removed
    foreign test while preserving every intended test. Repeat the full unit
    command and dedicated browser journey; keep failed hosted runs diagnostic.
