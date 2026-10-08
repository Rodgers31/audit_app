# Fiscal discovery source fixture — #137 integration gate

The exact failure was reproduced at combined commit
`4d0ba24b7c67f816eaa4a51932aafba1c1759809`: discovery returned no readable
editions instead of FY 2026/27 and FY 2023/24.

The download fake returned nonexistent relative paths. Source-bound fresh
parsing correctly rejected both as `unreadable(FileNotFoundError)`, including
when parse caching was disabled. Temporarily substituting the pre-trust
`1e2c2be` parse-cache helper made the original fixture pass: that old disabled
cache path ran the text stub without checking its source file.

Only the test fixture changes. It now returns owned temporary byte files and
maps their stems to the same retained fiscal text fixtures. Those synthetic
files are a downloader/parser seam, not publisher PDF evidence. Every original
edition, fiscal number, reconciliation and failure assertion is retained.

Additional discovery controls exercise enabled cache reuse without reparsing
and missing source files with cache enabled/disabled. Missing files remain
unreadable despite a text stub that could otherwise supply a valid edition.
That disabled-cache negative was red with the old helper, and green with the
existing source-bound implementation. No production parser, qualification,
receipt, source identity or cache policy changes are made.

Execution receipts:

- Original combined failure: `/tmp/fiscal-discovery-combined-red.log`.
- Original fixture with old helper: `/tmp/fiscal-discovery-pretrust-positive.log`.
- Missing-source negative with old helper (one failure, one pass):
  `/tmp/fiscal-discovery-missing-source-old-red.log`.
- Entire fiscal framework file: **43 passed**.
- Fiscal framework plus affected receipt/cache controls: **138 passed,
  5 skipped** (owned disposable PostgreSQL required), three existing warnings.
  The retained actual BROP/CBIRR PDF controls ran. Log:
  `/tmp/fiscal-discovery-receipt-cache-final.log`.
- Critical flake8 (`E9,F63,F7,F82`): **0 findings**.

The coordinator owns the remaining full combined/hosted CI gates. No production,
GitHub, Actions, migrations or deployment operations were performed.
