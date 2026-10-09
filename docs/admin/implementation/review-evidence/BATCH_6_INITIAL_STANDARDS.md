# Initial independent Standards review

Fixed base `dbfa7c100731fd2aa1ee4cc7b872a3ab600eaeee`; immutable reviewed heads and full diff/log/stat receipts are `{559,560,561,562}.{diff,log,stat}.txt`. Standards source: `TESTING_GATES.md`; each lane's committed implementation handoff. Full Fowler baseline read. Tooling-enforced trivia omitted. These are initial findings, not final repaired-head acceptance.

**Hard documented coding violations:** none established. `TESTING_GATES.md` deployment/full CI acceptance remains coordinator work; scoped author receipts do not prove full coverage/security/deployment gates.

**PR559:** Actual users audit helper bypasses PR562's bounded write projection: a synthetic legacy role containing `oauth_token=INERT_SECRET_FOR_PROBE` persists verbatim while the shared policy redacts it. Users keys also omit actor identity. Real React Query replay returns actor A's private cached row to B on same-key access; layout cleanup only depends on `isAdmin`. Confirmed integration discrepancies require repair. Import-mode/auth/event-loop findings agree with inspection. **Reject the redirect-body recommendation:** executing the locked official Supabase SDK places `redirect_to` in `/recover` query; current helper matches it.

**PR560:** Executed `OperationsRoute` returns hostile 401 diagnostic detail verbatim; 500 is sanitized. Executed parser accepts impossible February 30 and a one-source plan despite handoff promising validated six-source/bad-date rejection. Production planner path concern is supported by Docker context/path inspection. Repairs are being coordinated by Operations owner.

**PR561:** Small monitoring/native metadata product delta follows current private-policy/disabled-publishing boundaries; no additional actionable code finding. Existing operator docs omit the newly required explicit flag, agreeing with Copilot's documentation finding.

**PR562:** Executed audit wrapper sanitizes 401 but leaks hostile 500 JWKS detail. Overview decoder separately accepts malformed timestamp, one source and unknown source, so fixing only560 leaves a partial plan accepted here. Its users card claims profile-only counts while559 now counts Auth identities. Overview/audit actorless keys and layout cleanup permit the same cross-actor cache issue. Epoch predicate needs coordinator repair/verification; supplied old bookmarks have no check against current epoch.

**Heuristic:** possible Duplicated Code in three lane-specific private response wrappers; their differing error branches already drift. Separate users audit persistence also duplicates shared policy ownership. Consolidation is a judgment call; proven privacy failures are concrete defects.

Executed receipts: `hostile_backend.py`/`.output.txt`, `hostile_frontend.cjs`/`.output.txt`, `actor_cache.output.txt`, `recover_sdk.output.txt`. No product edits, Git mutations, external calls or resource lifecycle occurred.
