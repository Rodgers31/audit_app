# PR860 repaired OCR reader/cache — scoped pass

**All 16 unchanged independent cases passed normally and with actual `python -O`: zero failures/errors/skips (1.17s / 1.67s).** The original 8 desired REDs plus 8 passing controls are retained intact; the repair was tested against the identical read-only test file rather than altered expectations. No remaining finding in this assigned OCR/cache scope.

Frozen repaired input: `source-repaired-1`, **1,468 backend files**, canonical sorted mapping SHA256 **037875eb22c46cbbd784559a9c69e7cd05bb7b61a5d65cd9109cdec8cb9aeb45**. Every source file rehashed after execution with zero differences; five directly reviewed live source/dependency files still match the frozen pins.

- `fiscal_summary/fiscal_framework.py`: `a37dd8759593fc906d2e317fcc32dc1a9494b082b32834408961773a61d5cb60`
- `fiscal_summary/fetcher.py`: `5851e98aaab5264bd08164537c2084c8f5e63d75919c44092762e376ccd4b868`
- Global `parse_cache.py` remains unchanged: `aee9cf145d0045c89be7d9fad9b5ed80ceab88178a8e5bb5aa37817237032db1`.

## Verified closures

- Inline **4430767899**: both complete-single-row and short-row partial image text now attempt one bounded OCR call and reach the real edition/narrative/reconciliation/sign gates with a valid recovered table.
- Body-only **heading preservation**: row-only OCR no longer loses the known Annex 2a title. The independent historical FY2023/24 split retains its original **Actual** column qualifier. Source inspection confirms recognized original financial-row lines are excluded instead of blindly prepended to the recovered table; original nonfinancial heading context remains.
- Body-only **permanent OCR refusal caching**: timeout, empty and incomplete OCR results now remain explicit refusals but are retried on the next same-source/same-engine invocation. Recovery qualifies and actually applies **4785.2B** through the real financial gates. Persistent failure is also retried and still refuses. The typed extraction exception prevents banking unavailable records; the global cache implementation was not relaxed.

The eight original controls still pass: successful valid matching cache reuse avoids a second OCR call; changed source/engine identities recover; complete text requires no OCR; no-image partial text and ambiguous image pages refuse; broken OCR arithmetic refuses; disabled-cache retry/recovery remains correct.

## Evidence / boundaries

Exact owned Docker argv, literal exit codes, output, JUnit and per-case observations: `repaired-1/{normal,optimized}/`. Stable fixture: `test_review_ocr.py`; final unique per-case receipts: `repaired-case-ledger.json`. Source identities: `input-repaired-pins-1.json`, `source-repaired-manifest-1.json`, `repaired-source-after.json`. The original `REPORT.md`, `FINDINGS-RECEIPT.json`, source snapshot, test file, normal/O failure receipts and every previously pinned artifact were revalidated unchanged. The initial report remains explicitly an unaccepted pre-fix result.

Actual extraction wrapper, image preprocessing, edition reader, parse cache, financial gates and application ran. PDF pages/raster/OCR/version ports are controlled owned fakes. This bounded final phase makes **no new genuine-Tesseract/PDF acceptance claim**; root owns that separate runtime proof. Fiscal revenue coverage, same-year edition conflict, debt/GDP/source fallback, full fiscal-domain freshness, performance, production and deployment approval remain outside this scoped result.

All project execution stayed in cached offline Docker: **1 CPU / 1 GiB / 256 PIDs**, source and tests read-only. No product edits, installs, PG, project env/credentials, network/provider/production actions, publishing/uploads/workers, dispatch or control changes. Owned `--rm` containers are gone; shared containers and resources were not changed (`repaired-runtime-cleanup.json`).
