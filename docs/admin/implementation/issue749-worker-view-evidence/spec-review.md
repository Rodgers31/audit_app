# Independent Spec delta review — worker historical view parity (#749)

**CLEAR within this patch’s narrow acceptance contract.** Reviewed exact code SHA256 `2260d282036a42df0694c4dac208913b9b00892ae1e0a568e1ef3a82c0a4570f` at accepted main `1ce1d56b7e785735ed237f77afe9dee638b997e8` plus working delta. The patch adds one fixed locked-view digest (`a10869d…`) and permits it only for `social_report_source_authority`. Existing clean locked digest and the sole snapshot digest remain unchanged. No grants, schema, activation, client or provider logic changes.

## Substantive contract review

Read actual708 migration (`backend/alembic/versions/a708b15a0001_report_release_state.py:20–72`), current `_views`/`_verify` call chain, proposed formal regression, production-role/view diagnostics, raw owned actual-PG reproduction and original red outcomes. Independently recomputed the exact clean/historical/snapshot hashes. Every SQL byte outside the inner locked cohort SELECT projection is equal; all snapshot SQL bytes are equal. The modified inner projection is migration708’s `SELECT c.*` expanded in the known historical physical order with the preexisting validation_warnings and confidence_score. The outer cohort uses only id/source_document_id/period_id. Membership/provenance filters, date and qualification receipt joins, all row locks and exposed three-column shape remain unchanged. The base-record `to_jsonb(b)` continues to make historical column values part of the source fingerprint; this patch neither removes them nor asserts old and clean fingerprints are interchangeable.

The exact structural checks still precede hash membership: both owners, sole enabled `_RETURN`, security barrier/options, columns/types, both expected view rows and report_schema. The change does not normalize view SQL or accept arbitrary catalog drift. Existing schema-qualification normalization is unchanged. The historical digest cannot be used for the snapshot view.

## Independent executed adversarial controls

External `review_delta.py` executed **32 unittest methods normal and optimized**, all pass. Assertions use unittest checks (remain active under `-O`). Controlled catalog rows feed the real `_views`; raw view definitions came from the separately generated actual-PostgreSQL capture. These are branch/hash acceptance probes, **not this axis claiming fresh real-PG privilege/locking acceptance**.

- Positive clean and historical exact captures accepted; pre708 no-views accepted; post708 missing-views refused.
- Observed red: the exact historical capture is refused by the original accepted-main `_views`, while clean passes; changed code accepts both.
- Both locked variants substituted under snapshot name refuse.
- Extra SQL/comment bytes, changed SQL literal, altered cohort field/filter, removed/weakened entity/job/extraction locks refuse on both clean and historical definitions.
- Owner drift (including truthy non-Boolean), missing/extra/renamed/reordered columns, type drift, missing/changed options, added security_invoker, extra/changed RETURN rule flags, unknown name and missing snapshot refuse.
- Exact original constants/read-view allowlist remain fixed. `_views` executes only its two SELECT catalog reads under this probe.

Raw mode logs, source/capture hashes and independently recomputed semantic comparison are in `normal.log`, `optimized.log` and `RESULT.json`. Counts overlap formal/Standards selections and must not be summed into a broader suite claim. The assigned other axis owns the fresh clean/historical PostgreSQL install/login/negative privilege tests; this reviewer read the formal test and did not duplicate its resource controller.

## Limits and remaining conditions

Production-role diagnostic separately reports missing expected read grants; this hash repair **cannot grant or qualify them**. A later explicit reviewed operator action/verification would be required. The patch does not resolve whole-host shutdown/capacity699, provider access, Meta security checkpoint, tokens, custody or actual live metrics/publication acceptance. Publishing/uploads/native/supervisor stay off. No production/provider/credential access, database server, grant, build, image pull or repository source edit was performed by this review.

No confirmed new issue found in the delta. The generic historical/off-system media recovery limitation in the original-scope audit is unrelated and remains unchanged.
