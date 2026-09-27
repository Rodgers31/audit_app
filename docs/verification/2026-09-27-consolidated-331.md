# Consolidation #331 — 27 September 2026

Consolidates #335 into #331. The sole direct conflict in the entity list now preserves both public_entity_metadata(entity.meta) and financial_summary=summary. All source commits are retained.

## Focused verification

220 metadata, identity, accounting and API backend tests; 17 frontend tests; TypeScript passed. Four independent cross-change cases preserve zero/null and current/prior periods while refusing hostile metadata.

The sessions already ran broad tests and PostgreSQL probes; this pass concentrates on combined boundaries. No whole-repository re-audit or paid bot review was requested. Jest used forceExit for the existing open handle. New main-targeted CI is required on the pushed consolidation head.

## Remaining limits

All county metadata and legacy cleanup SQL remains a proposal. Remove remaining fixture writers, refresh snapshots and verify backup/recovery before execution. When later combining with #327, retain its sourced-project evidence gate using original storage through that gate, never raw public metadata.

No production deployment, seed, data cleanup or merge to main was performed. Source issues stay open where production acceptance is pending.
