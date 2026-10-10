# Draft publication verifier recheck

The frozen verifier `1f5e6f6c6fa12261520d6a8c53343a7c69972c4f569a892b9400ace406107ce1` closes all six independently reproduced metadata gaps. Earlier verifier copies and failing command captures remain unchanged.

On the immutable initial packet (`evidence-v1.zip`, SHA-256 `c52f8544689c025c4de5d4d9f623d2785e5dcbf22b968a09e38b6e6a8e898f37`), normal Python and optimized Python each passed 15 independent controls and all 30 author controls: **90 controls total**, zero failures, skips, or timeouts. The original three mutants now fail with the intended required-field diagnostics. Missing, empty, relative, extra, policy-breaking, colliding, shared-home/shared-config, and extra-PATH environments fail closed. Unsafe source inventory paths are rejected. Schema 2 requires an archived packet producer with a matching hash; legacy schema 1 remains explicitly classified as historical integrity.

Every command exited 0 and retained unchanged checkout identity at implementation HEAD `be1df5f3289d40a52703295a8a68efc054121662`. Raw stdout/stderr, actual exit/runtime/environment/source/producer metadata, exact copied verifiers, and independent controls are retained in this directory. Copied author tests differ only in their local verifier filename so they execute the frozen review copy.

**Outstanding findings: none in this external verifier revision.** This is a review of draft tooling and historical packet integrity. It does not imply current application acceptance, remediation of all advisories, or closure of issue #494. The final additive documentation and final schema-2 packet remain subject to recheck after publication.
