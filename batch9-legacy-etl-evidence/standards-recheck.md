# Independent Standards recheck

Original `standards-review.md`, `standards-session-red.json`, and `standards-readiness-red.json` remain preserved. Rechecked the working candidate against pinned base `9e97ca3f1ca43f103a8655447a86d889456a218a`; `etl/writer_ownership.py` SHA-256 is `c66e04d352a5782db434bbf508116d144a18af9d3afc93860039e9e194539054`.

**Both recorded findings are resolved in independent execution.** Unchanged controls passed on Python 3.13.9/SQLAlchemy 2.0.46 and Python 3.12.14/SQLAlchemy 2.0.23. Manual sessions close in creation order, release every claim, and permit another session. Storage missing the essential partial unique index is refused before any effect; its retained native claim remains.

Exact commands, source hashes, raw output and exit 0 are in:

- `standards-session-final-independent.json`
- `standards-readiness-final-independent.json`
- `standards-session-final-minimum-independent.json`
- `standards-readiness-final-minimum-independent.json`

Replay command shape: `<recorded-python> batch9-legacy-etl-evidence/run_receipt.py <receipt-name> <recorded-python> batch9-legacy-etl-evidence/standards-{session,readiness}-probe.py`. Each receipt expands this into its exact argv.

`standards-verify-receipts.py` read-back validates all four exit/verdict/source bindings and both unchanged probe generator hashes; result: `standards-replay-readback.json`. Replay generator SHA-256: `519b548f3760f324c3a44fa2616a2e56ff4819d6fa9f5909a94e0d14868011bd`; session generator: `d94462bc7f1d8551539f114e4d15ba83742bd18263eb890ac3d95e60ca07f605`; readiness generator: `23f7036fe38dfd4b07fd8842e889f724b3d3645abff520c183e6eedc3b271eeb`. An earlier read-back caught author source drift; its unsuccessful check is retained in `standards-readback-source-drift.txt`, and all controls were replayed against the updated source.

Static recheck found no additional documented standard violation. `note_failure` centralizes the discretionary duplication previously reported. Manual finalization tracks the last session independently of close order; decorated calls retain their own outer lifetime. The resolved-bind guard covers statement-specific routing, and external Connection binds, mapper/table rebinding, and raw connection escape refuse visibly. Schema readiness runs before acquisition, and acknowledgement still delegates to the unchanged shared transaction API.

These controls used only deleted temporary SQLite databases. They do not establish PostgreSQL process-race or production acceptance; the author's separate owned PostgreSQL suite and operational gates remain required. No implementation/tests, live services, GitHub state, or primary runtime files were modified by this recheck.
