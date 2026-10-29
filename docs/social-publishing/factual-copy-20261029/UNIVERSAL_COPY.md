# Shared social wording across counties and national sources

Nairobi is a demonstration of the shared engine. Production renderer and destination code contain no Nairobi-specific rule. The entity, metric, reporting period, unit, source and destination come from the record's evidence.

The earlier financial-v3 change covered qualified pending bills, national expenditure/revised budgets and revenue heads. This follow-up also modernizes every existing general-fact category and neutral report announcement. It does not claim that arbitrary unqualified documents can be ingested or summarized.

| Existing engine family | Current wording |
|---|---|
| Dataset availability, new report, debt/budget update, audit finding, correction | `factual-v2`: readable quantities, each entity/period, reported/modelled/projected distinction, reporting basis and attributed source |
| County budget implementation reports; native national budget, revenue, audit and pending-bills reports | `report-availability-v2`: a plain report invitation, exact scope and human-readable publisher date; no invented report findings or monetary stand-ins |
| KRA catalogue entries without a proven publication day | `catalogue-availability-v2`: explicit catalogue date and unknown report publication date; human review remains required |
| Qualified native financial records | `financial-v3`, with unchanged text after extraction of the common quantity helper |

The common Decimal formatter handles all existing source scales, including exact small values, magnitude carry and explicit approximation. It labels KES as KSh, preserves other units/currencies, and does not turn a ratio into a percentage or an estimate/projection into an actual figure. Multiple facts retain their individual entity, year, basis and source. No figures are added, combined or silently dropped to fit a platform limit.

Saved factual-v1, financial-v2/v3, report-availability-v1 and catalogue-availability-v1 revisions retain their pinned byte rendering. A wording change does not create a new source event or rewrite historical drafts. Human-authored posts retain their text; the existing preview handles any saved document/account override.

New wording versions cannot inherit old unattended-copy authority. Policy scopes now include the reviewed version, preserving the exact accepted factual-v1 scope hash. Operating evidence uses the immutable revision's version. Candidate and worker checks replay that same version. An old snapshot cannot authorize new wording; any future V2 automation requires its own accepted human outcomes and snapshot. Source eligibility, currency meanings, worker witnesses and global controls remain unchanged.

Links continue to use qualified identity. Pending-bills county destinations resolve the actual Loan → Entity slug and source reporting day. Other records retain their evidence's canonical destination; the engine does not guess a county from a name or invent unsupported URL selectors. The date-aware public reader in #853 remains a deployment dependency for the new pending-bills anchors.

The owner explicitly requested editing the existing Nairobi draft. That single draft was saved through the authenticated UI as revision 2, with the compact wording and county link, and verified after a fresh page load with its evidence and preview retained. It is unapproved and unpublished. No other production draft, source, control, worker or provider action was changed. General engine changes remain in draft PR #852.

## Verification

The focused 301-case set passes with optimized Python, including actual county/report/catalogue writers and current V2/legacy V1 policy/worker replay. The expanded normal run passes 387 cases and reproduces exactly the same 16 legacy SQLite source-witness failures as accepted baseline 74ca4da (baseline: 38 pass/16 fail); no new failure is introduced and no witness gate is weakened. The historical report test module's assigned old-schema cohort is not claimed as current-schema acceptance; current full-chain tests execute its real helpers on the guarded a756b20a0001 fixture.

Cross-entity coverage includes Mombasa, Kisumu, Garissa and national government; all six existing categories and source types; all native report families; actual/modelled/projected data; non-KES quantities; zero, small values, exact scales and rounding boundaries; catalogue unknown dates; correction markers; saved-version replay; and version-specific policy scopes. Actual PostgreSQL cases carry sealed offline source evidence through generation, immutable revisions, source checks, human review and installed worker-authority checks.

Examples in [UNIVERSAL_EXAMPLES.md](UNIVERSAL_EXAMPLES.md) and `universal-examples.json` are actual renderer output from closed fixtures, not production or source-qualification proof. Execution receipts, frozen manifest and independent Spec/Standards reports live in the task evidence folder as `universal-copy-*`. No merged-branch, production deployment, engagement, personal-voice or provider-presentation acceptance is claimed.

Final independent review: Spec passes 378 cases (201 independent controls plus 177 repository coverage/real-PG cases); Standards passes 230 independent cases. Both verify the exact frozen 1,426-file candidate, manifest SHA256 `ae919fd776c09d662371329f7af7bac9f9ce42231ddea216570b7bf866d92e33`, and report no unresolved product finding. Their reports are `universal-copy-spec-review/REPORT.md` and `universal-copy-standards-review/REPORT.md` in the task evidence folder. The real UI draft edit is separately observed author evidence, not an independent-review production attestation.
