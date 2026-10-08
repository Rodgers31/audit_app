# Human review packet: 58 new evidence UI translations

Status on 7 October 2026: **human meaning and fluency review pending for all 58 new keys**. The earlier approval of 144 strings does not approve this set. No reviewer decision or correction has been recorded for the new keys.

The [worksheet](2026-10-03-evidence-language-review.md) contains the exact current English, draft Kiswahili and plain English values for 36 initial evidence UI keys and 22 caller/county keys. The source snapshot is `2ed370312e7aa4f9c4ad6d91e8d5e9dbd6e7be93`, in `frontend/lib/i18n/messages.ts:28–86`. This documentation update leaves that complete source file byte-for-byte unchanged, preserving the earlier approved strings as well as quantities, digests and evidence statuses.

The editable reviewer CSV is `NEW_58_SWAHILI_REVIEW_2026-10-07.csv` in the shared session artifact directory `/Users/roger/.codex/visualizations/2026/09/27/01a0e1cf-a369-7b83-9e83-8d7900666170`. It has one row per key, the exact EN/SW/plain triple, usage context and source locations, plus blank reviewer decision and correction cells. The matching readable packet is `NEW_58_SWAHILI_REVIEW_2026-10-07.md` in that directory.

## Meaning the reviewer must preserve

Qualification here describes the status and limits of evidence for **this exact measured figure** and its individual measures. It does **not** denote a Kenyan qualified audit opinion. A source listing, publication, retained digest or byte check alone does not establish that the exact figure was verified. Check this meaning in `evidence.status.qualified`, `evidence.no_qualification`, `evidence.reason_unavailable` and `evidence.page.subtitle` together.

The checked source guard in `frontend/lib/evidence/qualification.ts:41` requires a complete identity and nonempty reason, then both `document_bytes_checked` and `value_checked` before selecting the verified label. `frontend/components/evidence/FigureEvidence.tsx:36` also uses the qualified label for an explicit qualified note with a nonempty reason. Human review of this copy certifies neither those underlying facts nor an aggregate of observations.

Preserve negation, missing-result wording and the distinctions between verified, incomplete, qualified, conflicting, modelled, projected and unavailable evidence. Read the byte/value labels as complete sentences. Keep placeholders `{label}`, `{kind}`, `{name}` and `{sector}` intact; substituted names, source facts, diagnostic identifiers, values, periods, units, locators, digests and URLs stay literal. `GDP` is the sole new SW value identical to EN, as a retained acronym.

The catalog has 58 keys but quoted production references cover 57: `evidence.page.this_observation` is an inactive draft retained in the catalog; the active exact-detail disclosure uses `evidence.label.this_observation` at `frontend/app/sources/figures/[table]/[id]/FigureEvidencePage.tsx:36`. Review the inactive draft too if approving the complete 58-key packet, without treating it as observed UI.

## Wording candidates for human decision

These are proposed review questions and alternatives, **not accepted corrections**. Runtime text has not been changed.

| Keys | Context to assess | Unapproved candidate or correction direction |
| --- | --- | --- |
| `evidence.status.qualified`, `evidence.no_qualification`, `evidence.reason_unavailable`, `evidence.page.subtitle` | Exact-figure evidence limits and status | Confirm that the current phrases communicate evidence limitations and cannot be read as a qualified audit opinion. |
| `evidence.publisher_unavailable` | Publisher information is missing | Consider `Taarifa za mchapishaji hazipatikani.` if the current `Mchapishaji hapatikani` suggests the institution itself is absent. |
| `evidence.source_kind`, `evidence.unknown_kind` | Combined fallback currently reads `Chanzo cha aina haijulikani` | Assess the combined grammar; consider `isiyojulikana` for the unknown-kind token. |
| `evidence.checked`, `evidence.not_checked`, `evidence.matched` | `Baiti za chanzo: …` and `Thamani: …` | Assess agreement in both sentences. If distinct forms are needed, request separate contextual keys rather than approving one replacement without considering both callers. |
| `evidence.label.gross_county_product`, `evidence.county.gcp_title` | Gross economic output of a county | Assess whether `pato la kaunti` preserves the gross scope; consider `jumla ya pato la kaunti` with domain review. |
| `evidence.county.headcount` | `poverty_headcount_rate` is displayed as a percentage | Confirm rate meaning; it is not an absolute headcount. Read with `0%` and the missing-value fallback. |
| `evidence.status.projected`, `evidence.page.refresh` | Future projection versus modelled estimate; refreshing the evidence request | Assess whether `Makadirio ya mbele` and `Onyesha ushahidi upya` express the intended distinctions and action clearly. |

## Technical receipt and scope

The local validator `NEW_58_SWAHILI_REVIEW_VALIDATE_2026-10-07.py` in the artifact directory reads the actual message source and worksheet, scans quoted evidence references and FigureEvidence calls under `frontend/app`, `frontend/components` and `frontend/lib`, and compares the CSV back to source. It does not execute the UI or certify wording. It checks exact SW/EN equality, not linguistic quality or every possible English fragment elsewhere in the application. Four unkeyed calls use raw API record or lender labels: RevenueMix, NationalLoansCard and two DebtPageClient rows. Their source derivation was inspected; the [caller inventory](2026-10-03-evidence-label-followup.md) gives the boundary.

Executed command: `python3 /Users/roger/.codex/visualizations/2026/09/27/01a0e1cf-a369-7b83-9e83-8d7900666170/NEW_58_SWAHILI_REVIEW_VALIDATE_2026-10-07.py`.

```text
PASS source keys: 58 (36 initial + 22 caller/county supplement)
PASS worksheet: 58 unique keys; exact EN/SW/plain source match
PASS language fields: 174 nonempty EN/SW/plain values
PASS interpolation: 5 keys; tokens preserved across all three modes
PASS caller/county references: all 17 label and 5 county keys referenced
PASS authored literal FigureEvidence callers: 16 explicitly keyed; 4 unkeyed calls use raw record/lender labels
PASS exact SW/EN equality: evidence.label.gdp only (retained acronym)
SCOPE 57 keys have quoted production references; evidence.page.this_observation is catalog-only
PASS reviewer CSV: 58 rows, exact EN/SW/plain, contexts present, decisions/corrections blank
PASS complete message source unchanged from 2ed370312e7aa4f9c4ad6d91e8d5e9dbd6e7be93
Message source SHA256: e1bfc76b894dccbbe9588142370fa368b0edb3c770d59e902f91faef9dd5b001
Human language approval: PENDING for all 58 new keys
```

Retained test logs were read for this packet, not rerun for these documentation edits. `REMAINING_EVIDENCE_LOCALIZATION_LOCAL/evidence-localization-final-jest.log` records `Test Suites: 2 passed, 2 total` and `Tests: 26 passed, 26 total`; its browser log records `5 passed (18.5s)`. `REMAINING_EVIDENCE_CALLERS_LOCAL/evidence-callers-green.log` records `Test Suites: 5 passed, 5 total` and `Tests: 46 passed, 46 total`. These files are in the same artifact directory. The test source covers selected language switches, states, zero values, literal substitutions and preserved links/selectors. The 26 and 46 results overlap and must not be added as unique test coverage. Prior documentation records lint and typecheck success; their empty logs alone do not establish exit status. None of these results constitutes human language approval or production evidence verification.

## Completing human review

A competent Kenyan Kiswahili reviewer should review all 58 CSV rows against their supplied contexts, record `accept`, `correct` or `needs domain review`, and give exact proposed replacement text for corrections. Record reviewer identity, review date, scope, remaining concerns and final decisions with the completed packet. For contextual changes, review the assembled sentence and its raw substitutions, including dollar sequences and placeholder-like text.

Reviewer: **pending**. Review date: **pending**. Approved new keys: **0 of 58**. Automated preparation and technical checks do not fill these fields. The earlier 144-string approval remains separate; this packet does not authorize closing an issue or claiming acceptance of the new translations.
