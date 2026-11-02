Independent frontend and API-client review is clear at the source hashes in REVIEW-RECEIPT.json. Production publishing, uploads, workers and financial generation were not operated by this reviewer.

The private suite executes the real AccountPublishingControl component, real account-read and command API wrappers and real response decoder; only authenticated transport and auth context are replaced. It passes 19 cases after the author reproduced and fixed five initial failures. Initial source-bound RED logs remain retained.

The initial failures were three mutation responses with an unchanged/unrelated controls version or unchanged account state token being accepted, a missing global-off hold being decoded as coherent, and two same-frame refresh calls allowing an older ready response to overwrite a newer credential hold. The final code requires the exact next version and changed token, enforces global hold consistency and synchronously locks both reads and mutations. All five counterexamples now refuse false success.

Additional executed cases cover wrong account identity, malformed booleans, zero/fractional/NaN/infinite versions, malformed state hashes, missing flags, contradictory enable blockers, exact key/body reuse after ambiguous transport, no optimistic enable, signout/account-change late-response suppression and pause availability with unusable credentials. Normal account consent remains explicitly separate from global publishing and worker readiness.

The author's focused component suite was also executed independently: 17 passed. It is reported separately from the 19 private cases, since coverage overlaps. Parent's broader tests and backend review remain separate evidence; this review does not add those counts together.

The manual-activation document correctly separates implementation from activation, queued from published outcomes, stored credential metadata from provider validation, and local synthetic evidence from production media/worker custody and capacity. The two connected account rows in the retained production posture do not establish two distinct Page credentials, so the parent was asked to use account-neutral credential wording.

Execution used cached Node24.22.1 and the existing installed Next/Jest/jsdom toolchain without installation. This is component/API-client behavior qualification, not a hydrated-browser visual or provider/live-database acceptance. No browser fixture for this new control was supplied; no checkout files, dependencies, provider settings, jobs or production records were changed by this reviewer.
