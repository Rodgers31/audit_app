# Nightly refresh gap repair — 31 October 2026

The [scheduled refresh](https://github.com/Rodgers31/audit_app/actions/runs/41158948256)
completed, but its execution status overstated source coverage. It ran before
the #859 deployment, on `e1a0d6b`, and committed jobs 3553–3567. Publisher-backed
jobs retained 111 captures with none missing; pending bills processed 48 rows
and retained six captures without the previous lineage failure. Those results
do not establish that every fiscal component or historical debt year refreshed.

This repair builds on `1502e39`. It changes no publishing, upload, worker,
financial-generation, dispatch or infrastructure setting. It requires no new
service, credential, resource, model or paid review. The seed workflow already
installs Tesseract; both backend images now include the same free system OCR
engine and English language data so ordinary admin jobs have the capability.
No package was installed into the running production service. Tests used capped
local containers and a disposable PostgreSQL database.

## Repaired behavior

- Request enough World Bank GDP rows for the complete history. Preserve the
  complete-response guard, require integer pagination metadata, and reject
  boolean years and invalid GDP denominators. Partial debt or GDP coverage is
  explicitly partial. Clear stale ratios after debt refresh when GDP fails,
  is missing/zero, or is disabled.
- Carry CBK stock observations and their sealed acquisition evidence through
  the overlay, parser and writer. Cite the acquired bulletin URL. Reuse a source
  only with the correct country, document type, URL and publisher; preserve
  older and unrelated source documents without relabeling them.
- Read a single titled image annex using bounded local OCR: one page, at most
  12 million rendered pixels and 20 seconds. Retain edition, column-identity
  and arithmetic checks. Conflicting covers/annexes, non-finite cells, negative
  spending components and interest exceeding recurrent spending are refused.
  Negative or unreconciled tax components withhold the tax split separately.
- Bind cached extraction to the actual extractor file, PDF/OCR/render package
  versions, Tesseract version and English-language capability. Bypass caching
  when that identity cannot be established. A source or dependency change can
  withdraw a previously accepted cached edition.
- Require the native CoB headline to explicitly name the National Government's
  original gross budget for the report's own fiscal year. Revised,
  supplementary, other-government, prior-year and conflicting amounts cannot
  become that measure. General text utilities retain their broader scope.
- Refuse unqualified collection scalars instead of proportionally inventing
  tax/non-tax components. Calendar-year World Bank actuals cannot create
  fiscal-year appropriation/ordinary-revenue estimate stubs. The native fiscal
  fetcher stops those four unqualified requests; qualified Treasury producers
  remain in place. Missing plausibility guards refuse promotion.
- Persist component and edition coverage in ingestion metadata. A budget
  update cannot hide missing revenue, framework, tax split or historical
  editions. The actual workflow summary names partial sources and ingestion
  warnings rather than ending with an unconditional success claim.

## Verification

The [manifest](2026-10-31-refresh-gap-repair.json) pins changed source bytes and
the retained command/XML receipts. The combined application selection executes 750 tests
in normal Python and the same 750 in actual optimized Python: zero failures,
errors or skips in either mode. This includes all 113 PostgreSQL
source-identity cases, using a disposable loopback fixture. Earlier missing
fixture/read-only-cache setup failures are retained separately and are not
counted as product regression proofs. A separate runtime guard suite executes
16 cases per mode. Its prior pipeline guard was seen to ignore a failing OCR
binary; the repaired shell preserves that failure and skips cleanup. The exact
production APT block executed successfully in a fresh capped local runtime,
and both genuine PDFs passed again as an unprivileged user. This is an
APT/capability qualification, not a full production image build.

Independent executable reviews cover debt/GDP/provenance (72 cases per mode),
OCR/cache/financial gates (68 per mode, including two genuine PDFs), and the
native fiscal/source/workflow boundaries (65 per mode). A separate runtime
review passed 16 shell controls per mode and two actual nonroot OCR controls. Their counts overlap with the root
selection and must not be added into a distinct-test total. Findings were
reproduced before repair; earlier failing receipts remain retained.

Actual Treasury source bytes were rendered, visually inspected and processed
with Tesseract 5.5.0 and PDFium. Both editions pass narrative/column selection
and seven checks through the existing financial split reader:

| Treasury source | Annex page | Expenditure, KSh billion | Source SHA-256 |
| --- | ---: | ---: | --- |
| [FY2021/22](https://www.treasury.go.ke/sites/default/files/Budget%20summary/29.04.2021_Final-Budget-Summary_TP.pdf) | 57 | 3,053.5 | `cc42b631ac9f8c92c51153dcc73c17ab677253d328d1f444e8e5743ae5571eda` |
| [FY2022/23](https://www.treasury.go.ke/sites/default/files/Budget%20summary/Budget-Summary-for-the-FY-2022_23.pdf) | 58 | 3,342.8 | `9a59476df81d5cce4aadf66c8ebd6db41c617c6ee9c726895c45850dd5654655` |

These are fiscal-framework expenditure totals, not CoB gross appropriations.
The editions do not establish an accepted tax split; that absence remains
explicit. Local source parsing is not a claim of production persistence or a
successful new live provider refresh.

## Remaining source and rollout gates

1. Treasury's listed FY2024/25 and FY2025/26 `oldsite` links fail certificate
   hostname validation; the corresponding indexed `www` and bare-host paths
   return 404. The current public listing, search and Bajeti Yetu catalogue
   were inspected. Parliament's FY2025/26 scan was acquired and its cover
   confirms **30 April 2025**; equivalence to the missing June Treasury `F`
   edition is unproven. Do not silently substitute a different vintage or
   bypass TLS. These sources remain unavailable.
2. The latest CBK bulletin refreshes four of the thirteen historical debt
   stock years. Older rows need their own retained source/period contract to
   become refreshed evidence. Successful GDP acquisition cannot qualify them.
3. Fresh bounded World Bank country-data probes timed out. Valid indicator
   metadata was obtained, but this is not a successful new GDP acquisition.
   Response/request behavior has executable coverage; real provider recovery
   must be observed separately.
4. The nine OAG combined-volume date/scope refusals and two bounded document
   deferrals remain part of #802's source rollout. The four malformed CBK bond
   rows and anomalous inflation remain withheld by existing guards. No
   invented publication date, borrowing balance, source value or artificial
   replacement is introduced.

The production readback at 05:11 UTC still reports release `1502e39`, publishing
and all approval/scheduling/publication controls false, media false, financial
generation unset/default-off, no worker/consumer, five drafts and zero targets,
publications, publish attempts, media assets or uploads. Repository financial
generation remains absent/default-off. A separate production capability probe confirms that the current image lacks
the Tesseract binary. The candidate image repair must be deployed before OCR
can work in an ordinary admin job. The local cached Python runtime is 3.12.15;
production currently uses 3.12.16. Local execution is not a claim of byte-for-byte
production runtime parity. The candidate has not yet been merged,
deployed or admitted for production ingestion, and no hosted validation was
dispatched for this repair.

After review and an authorized merge, deploy the exact accepted release, verify
the four shutdown controls again, and admit the matching ingestion SHA only
after the release checks pass. Inspect the next ordinary bounded run. A
production refresh and the remaining #802 source acceptance are still required;
this PR does not establish that the overall source rollout is complete.
