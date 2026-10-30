# PR856 marker comments: frozen4 scoped acceptance

No remaining finding in this edge review. All 5,806 frozen files and exact file set match mapping d4551375c41807a1856482607ea40496da2d766788290b67be6f8f833fcbd139 before and after execution.

**22 pytest cases passed, 0 failures/errors/skips,25.10s.** One case additionally executes 32 malformed typed-receipt scenarios and 2 valid-marker positives; those are scenarios within that case, not 32 additional pytest cases. Exact commands, XML, logs, source hashes and scenario JSON are adjacent.

The three independently observed behaviors are repaired: in-range wrong counts refuse before authorizing Nandi or silently repairing the marker; privileged partial v1→v2/count1 promotion refuses; ordinary partial later-period progress preserves the completed receipt/job/count/fingerprint while allowing top-level observed chronology to advance. The new-format independent accessor reads only the completed portion, excluding the intentionally mutable watermark. Original pre-fix RED fixtures/logs remain unchanged in the parent evidence directory; no claim is made that representation-specific assertions ran byte-for-byte unchanged.

All 14 permanent PR-comment cases pass, including 4 in-range counts, actual later-period 2 commits + 3 on resumption+unchanged replay, 7 membership/scope corruptions, partial-marker promotion and the publisher-cardinality control. Separate meaningful Nandi/new-row, retained-refresh/known-change/replay and prior newly-qualified-head chronology controls pass.

Independent typed edges cover count/type/length, root/completed job mismatch and booleans, fingerprint binding of valid-looking member/date/job changes, exact member keys, duplicate IDs/source keys, ordering, bounded IDs, wrong family/uppercase digest, extra/missing receipt fields, and watermark below completed dates. Malformed shapes are also tested with recomputed fingerprints where meaningful, proving structural validation rather than only stale-hash rejection. A later valid watermark preserves the completion and fingerprint. The actual v2 partial-progress control then acquires genuinely qualified older KRA evidence and verifies it is refused by the advanced watermark, retaining the prior completion. Known changes and replay still behave correctly.

Classification remains narrow: inline 4425754541 is valid persisted-state integrity hardening that originally required privileged cursor corruption; its claimed source/publication bypass was not reproduced. The body-only completed-date mutation was valid normal-flow attestation drift. Separating completed receipt from observed chronology fixes that invariant without reintroducing regressions by freezing the chronology watermark. No source qualification, approval or worker gate is weakened.

The receipt contains bounded exact sorted record-ID/source-key membership. Its count/job/dates/identity are fingerprint-bound; only finalization replaces it after current issued witnesses pass. AST comparison confirms unchanged finalizer database calls; new work is local receipt/hash metadata, with no old-job reread or added per-record database round trip. This review does not claim the broader latency suite ran here.

Execution used the existing owned capped offline PG17 fixture and cached read-only runtime; no parentPG, grants, workers, product edits, GitHub/provider contact, paid service or production action. Production deployment and the two real cohort checks remain root's separately authorized work.

Owned PG and private mode600 credentials removed after the final run; absence verified before receipt.
