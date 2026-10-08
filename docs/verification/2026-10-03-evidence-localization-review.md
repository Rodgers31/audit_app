# Evidence localization review — PR #495

Baseline: `2376b07b8f4f570dc0dc90352defdfcf03f43e64`.

| Copilot comment | Classification | Actual correction |
| --- | --- | --- |
| 4175752331, evidence detail page | Valid | Route title, subtitle, source-index link, loading/error/invalid states, retry/refresh controls, stored-value label and absent-value fallback use LangProvider keys. |
| 4175752373, shared FigureEvidence disclosure | Valid | Summary, individual evidence statuses, checks, source/detail links, locator/digest labels and missing-data fallbacks use LangProvider keys. |

The qualification guard still requires the same complete identity, nonempty reason and both independent checks before displaying the verified status. Its new message-key function preserves the existing English compatibility label. No qualification state or public quantity was reclassified.

The shared component is the localization boundary for its dashboard, debt, budget, county profile/list/comparison and exact-detail consumers. Caller-supplied record labels, publisher names, identities, units, periods, measure/reason identifiers, locator payloads and digests keep their prior data rendering. Source/exact-detail URLs and selectors are unchanged. Arbitrary source text is not passed through translation lookup. Template substitution also preserves literal dollar sequences in caller labels.

## Executed receipts

- Six new LangProvider language-switch regressions were run against the unchanged baseline and **all six failed** because SW/plain modes still displayed English. These cover both comments, exact value zero/selector preservation, invalid reference, absence and request failure.
- Final targeted Jest: **26 passed**, comprising 9 new language/state regressions and all 17 existing evidence DTO, hostile URL, incomplete/malformed verified refusal, aggregate qualification, zero and explicit refresh downgrade/failure cases.
- Scoped ESLint: passed for both components, qualification helper, messages and both new test files.
- TypeScript `tsc --noEmit --incremental false`: passed.
- Production Next build plus bounded Chromium: **5 passed**, comprising 2 new actual language-control/detail/refusal cases and the 3 unchanged original Sources cases. Language changes preserve zero, source facts and exact links without refetching. Invalid references issue no verification request. An initial browser assertion found both the page alert and Next route announcer; the regression now selects the localized refusal alert and retains its exact text assertion. No force click, timeout, retry or skip changes were made.
- `git diff --check`: passed.

Author Jest used a temporary runtime-only module map to make cached React/React DOM resolve to one author-tree copy; no repository dependency, production import, Jest configuration or original test changes were made. The map and executed logs are retained in the shared artifact directory `REMAINING_EVIDENCE_LOCALIZATION_LOCAL`. Root owns fresh-dependency and frozen hosted consolidation gates. These synthetic browser API observations do not claim production evidence verification or publisher signoff.

## Language review and scope

The [new Kiswahili worksheet](2026-10-03-evidence-language-review.md) lists all 58 newly authored draft keys: the initial 36 evidence UI keys and the 22 caller/county keys in the [follow-up](2026-10-03-evidence-label-followup.md). Technical checks cover shared localization and selected callers. On 7 October 2026 (America/Chicago), the human user in the coordinator chat explicitly approved all 58 existing drafts without corrections; the [approval receipt](2026-10-07-evidence-swahili-approval.json) records the exact scope and statement. This satisfies the language gate only, without data or provider certification. The [7 October human review packet](2026-10-07-evidence-swahili-review.md) includes the reconciled scope and contextual review instructions. Earlier approved 144 strings and closed #307/#372 work are unchanged.

No additional defect requiring a new issue was identified in this bounded review. No new issue or review-thread mutation was performed. No GitHub, Actions, provider or production writes were made.
