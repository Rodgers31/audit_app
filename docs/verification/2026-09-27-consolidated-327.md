# Consolidation #327 — 27 September 2026

Consolidates #330, #333 and #336 into existing #327 with all source commits preserved. Automatic merges touched main.py, the pending-bills fetcher and frontend types.

## Focused verification

202 preservation, citation, edition and revenue backend tests; 18 frontend tests; TypeScript passed. Independent probes exercised page-only reissue, refused truncation and shared resume plus edition selection.

The sessions already ran broad tests and PostgreSQL probes; this pass concentrates on combined boundaries. No whole-repository re-audit or paid bot review was requested. Jest used forceExit for the existing open handle. New main-targeted CI is required on the pushed consolidation head.

## Remaining limits

New confirmed follow-up #337: stale ORM state can let an old reconciliation approval overwrite newer evidence. The executable reproduction is in backend/scripts/reproduce_reconciliation_stale_session.py. Refresh-only is insufficient; fresh serialized validation/application is required. Keep this visible for Copilot and release review. Backend deployment must precede updated seeds; #318 stays separate until deployment and backup.

No production deployment, seed, data cleanup or merge to main was performed. Source issues stay open where production acceptance is pending.
