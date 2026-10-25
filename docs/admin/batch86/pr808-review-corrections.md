# PR808 review corrections — Batch 87

Reviewed frozen head `c622e004d09715b677972c621016169ea05905dc` against base
`a459834e31280b1e81b0604d16d687bc9ad7fffe`, including review 5645447689's
four body findings and inline 4372544682. The source/activation matrix and
remaining #802 work in [the handoff](draft_authority-handoff.md) still apply.

| Finding | Classification | Suggested fix assessed separately / result |
| --- | --- | --- |
| Malformed retained PDF escapes parser refusal | Valid | Accept catching the installed parser errors. Catch pdfplumber 0.11.10's `PdfminerException` wrapper and the underlying `PDFException` family around actual PDF opening/page extraction. Four real malformed-byte cases failed on the frozen head and now return the explicit refusal. |
| Nullable source metadata fails the later update | Invalid; executed refutation | Normalization was already performed before the later update. An existing source row set to SQL NULL updates successfully on the frozen head, retains one source identity and passes the exact committed reader. Keep the executable control; no speculative writer change. |
| Transaction-start time falsely refuses completion after a lock wait | Valid | Accept statement/clock time. Use `statement_timestamp()` in the separate validation query after authority locks. A real PostgreSQL advisory-lock wait reproduces the refusal on frozen code and passes after the fix. The existing future-completion refusal remains green. |
| Harness lacks inert auth setup | Valid | Accept a standalone auth/transport setup. Add a tracked launcher with fixture-only auth/session aliases and an explicit loopback API. The unchanged component rendered HTTP500 without auth setup; the launcher renders HTTP200 and exercises the actual components/API. Product auth is unchanged. |
| CoB-specific native timeout diagnostic (4372544682) | Valid nit | Accept domain-neutral wording. Three native-domain controls failed on the frozen message and pass with `Bounded ingestion identity required`. |

The nullable metadata suggestion was unnecessary for the actual control flow.
The PDF suggestion needed the installed pdfplumber wrapper as well as the
underlying parser exception. Catching `PDFException` alone was executed and
remained red; it is not passing evidence.

Verification retained locally under `BATCH_87_REVIEW/808`: frozen backend review
cohort **8 failed / 1 passed**; corrected native/review cohort **62 passed**
normally and with optimized Python; selected affected backend regression
**96 passed**; frontend generation cohorts **26 passed**; matching-lock
TypeScript passed. The real lock wait and SQL NULL control use owned PostgreSQL17
at unchanged Alembic `a756b20a0001`. Counts overlap and are not added.

The standalone launcher regression renders the actual harness with inert auth,
checks a local API read, proves no bearer/cookie forwarding, and refuses control,
upload and publication commands at the proxy. The root-owned Chrome check used
the real local API/PostgreSQL and unedited retained KRA FY2024/25 bytes; preview
returned unchanged without another draft. No production acceptance follows.

Full publisher-day/scope/country/artifact/receipt/job checks, financial
qualification, unknown-effect telemetry and neutral templates remain intact.
KRA FY2024/25 remains qualified; the current KRA dashboard and CoB annual report
remain held. Pending bills and borrowing stay unsupported. Issue 802 remains
open. No model, migration, grant, dependency, production configuration, workflow, source
activation, automatic retry, publication or upload change is included.
