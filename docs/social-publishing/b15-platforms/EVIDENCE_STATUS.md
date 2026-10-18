# Evidence status

The original TikTok, PostgreSQL and connection subtask receipts are **SUPERSEDED FOR CURRENT ACCEPTANCE**. Each has an adjacent `.superseded.json` declaration binding the original file hash. Original JSON/log bytes are retained. Earlier pass/count fields and earlier remaining-work statements describe historical candidates, not this integrated tree.

Do not execute `tiktok_capture_evidence.py`, `platforms_capture_postgres_evidence.py` or `backend/tests/social/platform_connections_verify.py` as supported acceptance tools. They inherit ambient inputs and/or overwrite fixed output paths and lack the final full-corpus/JUnit boundary. Their source bytes remain only to preserve historical provenance. Old command instructions in the historical subtask handoff are superseded by this notice.

Current evidence is the append-only `final-20261016T201824Z-2e59c5e5` directory linked from checkout HANDOFF.md: copied generator SHA256, exact argv/cwd, explicit inert environment-key allowlist,331 source hashes before/after, raw logs, JUnit/structured Jest output, exit statuses, readback-verified receipts and preserved baseline failures. No global acceptance verdict is fabricated from child process exit.

The preceding `final-20261016T201649Z-fd35b55f` remains an observed-red record: normal and optimized runs each found the widened image byte-ceiling regression. The corrected run preserves8MB images/100MB inspectedMP4 and passes the existing regression. Intermediate module-missing or fixture setup failures are not relabeled behavioral regressions.

Final independent Spec/Standards reports and a later material-limit addendum identify their exact source scope. Earlier review manifests affected by the material change have explicit supersession records; the current addenda and final root replay cover the corrected source. See HANDOFF.md and VERIFICATION.md for counts, limitations and current paths.

Raw historical `.txt` outputs and the two old docs capture scripts were moved byte-for-byte to external `platforms-evidence/delivery/historical/` to keep fixture transcripts out of the product diff. `archive-index.json` maps every original path to its preserved absolute path and SHA256; filesystem readback verified each copy before removal. Historical JSON receipt bytes remain here with supersession sidecars. The old backend connection recorder remains only for provenance and is unsupported.
