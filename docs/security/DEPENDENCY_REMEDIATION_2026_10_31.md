# Dependency remediation — 31 October 2026

Base: `178ff97d8a593ed8a152366cfdb446a29b434a45`, freshly fetched from `origin/main`.
Implementation uses an owned managed checkout; the dirty primary checkout and
other admin/source branches are untouched. Issue [494](https://github.com/Rodgers31/audit_app/issues/494)
remains open. This is partial remediation with explicit upstream blockers, not
an assertion that the application or its deployed environments are vulnerability-free.

## Current advisory inventory

The owner's complete 21,087-byte audit attachment has SHA-256
`139a6023037c9fe196cc1362b012335928f0bb2d5732527a83057a03ef5511d9`.
It reports 53 affected package entries. It describes an older installed graph:
Next, Transformers/ORT/AdmZip/Sharp, Axios, browser tooling, URI/YAML/PostCSS,
protobuf and source-map fixes already exist in main. The per-advisory
[reconciliation](dependencies/2026-10-31/owner-audit-reconciliation.json) retains
every distinct GHSA ID, including findings absent from the fresh baseline and
the newly reported glob cancellation advisory. Absence from a current package
audit is scoped advisory evidence, not proof an old exploitation path was reachable.

| Clean resolved scope | Before | Candidate |
|---|---|---|
| Full npm lock audit | 37 entries: 1 low, 34 moderate, 2 high | 22 entries: 5 low, 17 moderate |
| Production npm audit (`--omit=dev`) | 2 high entries, one redirect advisory root | 0; actual exit 0 |
| Backend runtime | 87 distributions, 0 OSV matches | 87 distributions, 0 OSV matches |
| Backend development | 129 distributions, 0 matches | 130 distributions, 0 matches; includes an explicit pyasn1 compatibility probe |
| Legacy ETL | 52 distributions; pypdf has 7 GHSA matches | 0 matches; 57 distributions including five test-tool distributions |
| Restricted worker fixture pins | 90 pins; 5 affected package names | 93 freshly installed pins, 0 matches |

The installation-time npm summary was 36 entries; the explicit subsequent full
lock audit reports 37, including optional-platform propagation. These are
package entries, not independent exploits. Full and production raw JSON,
complete Python version inventories, query counts/timestamps, results and input
hashes are retained in [the evidence directory](dependencies/2026-10-31/).
OSV queries covered every exact named distribution, including pip, without
advisory exclusions. Alias IDs in worker results are retained, not counted as
independent vulnerabilities. All captured queries completed; outages or skipped
queries have not been converted into zero findings.

## Changes and compatibility

| Area | Before → candidate | Rationale and actual callers |
|---|---|---|
| Axios transport | follow-redirects 1.16.1 → 1.16.2 | Patches [cross-realm sensitive-header stripping](https://github.com/advisories/GHSA-mrwp-f3q8-3g9p). Axios uses this Node adapter; the app does not currently declare custom `sensitiveHeaders`. |
| Modern glob callers | glob 13.0.6 / 10.5.0 → 14.0.3 | Exact version-scoped override for `glob@>=9 <14.0.2`; patches [post-abort traversal](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4). Jest config/reporters/runtime and test-exclude consume named modern sync/Promise APIs. Legacy glob 7 is excluded. |
| Modern match callers | minimatch 10.2.6 / 10.2.4 / 9.0.9 → 11.0.3 | Exact version-scoped override for `minimatch@>=9 <11.0.1`; patches [pattern amplification](https://github.com/advisories/GHSA-g3hv-75wg-m249). Covers modern glob, TypeScript ESLint's default-project matching and coverage test-exclude. Legacy minimatch 3 is excluded. |
| ETL PDF | pypdf 6.21.2 → 6.21.4 | All seven current advisories fixed across [6.21.3 and 6.21.4](https://pypdf.readthedocs.io/en/stable/meta/CHANGELOG.html). Actual KNBS fallback uses PdfReader; Camelot also resolves this pin. |
| Python constraint | pyasn1 floor 0.6.4 → 0.6.5, same `<0.7` ceiling | Fixes four new ASN.1 complexity advisories if the package is requested. Normal backend runtime no longer needs this jose-era transitive. A direct DER encode/decode probe executes 0.6.5 separately. |
| Worker fixture | Historical 20 October graph → fresh runtime plus fixture tools | PyJWT replaces unused python-jose/ecdsa/rsa/pyasn1; Pillow 13 and pip 26.2.2 replace affected historical pins. Includes current FastAPI 0.156.8/Starlette 1.9.0, Pydantic 2.14.2, SQLAlchemy 2.0.55, pandas 3.1.0 and NumPy 2.5.4. All 93 exact pins install through the real bounded installer and pass pip check. |
| Fixture discoverability | requirements.lock → requirements.txt | Supported Dependabot filename; Docker still maps it to the installer's fixed `/input/requirements.lock`. No installer/path guard is relaxed. After validating every row, the installer now prioritizes its declared pip pin before all other packages, avoiding 48 installs through the historical base installer. |

These scoped overrides deliberately cross modern callers' declared major ranges;
they are compatibility exceptions, not claimed supported parent-range updates.
Their complete caller graph and 36-record lock delta are retained. One new
`@isaacs/nonrecursive-glob-match` package and 21 retired CLI/support records account
for most churn. npm also removes only the `dev` flag from unchanged optional
Playwright fsevents 2.3.2, reflecting Next's optional Playwright peer path. It does
not change that binary/version. The only changed production package version is
follow-redirects. No global legacy glob/minimatch substitution, forced downgrade,
audit suppression, package-manager migration or disabled lifecycle check is used.

The [glob changelog](https://github.com/isaacs/node-glob/blob/main/changelog.md)
was checked across 10→11→12→13→14: Node support, CLI removal, matcher/ignore/Windows
semantics and cancellation changed. The [minimatch changelog](https://github.com/isaacs/minimatch/blob/main/changelog.md)
was checked across 9→10→11: named exports remain; RegExp/makeRe/AST internals are
removed in 11. Inventoried modern callers use the retained public methods. Tests
exercise cancellation, dotfiles, braces, extglobs, coverage includes/excludes,
sync/async traversal and actual TypeScript/ESLint/Jest behavior. Windows is not
qualified. No CLI consumer or new product feature is adopted.

The pypdf patches change parser termination/work bounds, page-label caching and
CID width handling. Existing text/table numbers are asserted unchanged by real
pypdf/pdfplumber/Camelot fixtures. No extraction mode, source data, admission rule,
auth/JWT/issuer policy, UI or financial calculation is changed.

## Explicit residual blockers

* **deepmerge 4.3.1**, [GHSA-gcqx-w48m-w2h4](https://github.com/advisories/GHSA-gcqx-w48m-w2h4):
  no patched published release is listed. Latest Jest 30.5.2 still requires it
  through jest-config (the config loader merges repository-authored options).
  Its low-severity root propagates to five package entries. No public application
  request caller was found. We retain the finding; downgrading Jest or deepmerge
  to escape an advisory range is not a repair.
* **minimatch 3.1.5**, the same amplification advisory's `<11.0.1` range: legacy
  ESLint/eslintrc/config-array, import/react/jsx-a11y plugins and glob 7/rimraf
  still require the callable/RegExp contract. The current plugins still declare
  3.x; even current ESLint 10 declares minimatch 10. A real ESLint
  `import/no-internal-modules` probe succeeds with the existing dependency and
  fails at `makeRe` when minimatch 11 is substituted. Version 11 removes that API.
  A broad override is therefore refused. The advisory's specific optimization
  mechanism concerns newer minimatch, but its published older-version match is
  retained without a suppression. Existing bounded repository tooling-input
  guards remain enforced. Seventeen moderate propagation entries remain.

Safe completion needs patched compatible legacy releases or an owned migration/
replacement of these upstream consumers, plus fresh complete acceptance. The
existing two-package source-bound braces/js-yaml postinstall repairs, all exact
hashes, caller checks and runtime/browser/native boundaries remain intact. No
residual-risk exception or issue closure is assumed.

## Verification and runtime boundaries

Verification uses official SHA-256-checked Node 24.22.1/npm 11.19.1 on macOS arm64,
and fresh venvs on an owned Linux arm64 Python 3.12.16 container. Standard-library
OpenSSL, wheel crypto/image codecs, PDFium and full Debian package metadata are
recorded separately. The reused cached image is a toolchain, not a claim about
current production OS packages. Tests see only inert configuration; networking
is disconnected from the Python container after package installation. There are
no production credentials, live database connections, workers or source jobs.

The following author gates executed successfully; overlapping selections are not
added as unique coverage. Final source identities and replays are recorded in the
PR delivery.

| Gate | Actual result |
|---|---|
| Clean npm ci, installed peer/engine graph | Pass; lifecycle repairs execute; npm ls --all has no problems/extraneous packages |
| Node dependency controls | 143 pass; separate runtime/isolation selection 9 pass (nested controls overlap) |
| TypeScript, lint, production build | Pass; inert backend failures during prerender remain expected diagnostics |
| Complete Jest | 215 suites, 2,897 pass, one existing pending |
| Admin shell Chromium | 12 pass across desktop/mobile widths and signed-out/editor refusals |
| Native model/images/ZIP | Actual CPU model inference, Sharp SVG/PNG/WebP and installer extraction pass |
| Production routes and semantic browser | Health/home/Learn/image return 200; real fallback and WASM search preserve sampled Articles 142/43; zero unexpected requests/page errors |
| Backend auth/issuer/TLS/PDF compatibility | 314 pass, zero skips; optimized auth selection 89 pass (overlap) |
| ETL real PDF readers | 5 pass, zero skips, including normal and true optimized EOF children |
| Image/media boundary selection | 141 pass and 9 video prerequisite skips in each normal/optimized mode; actual PNG/JPEG child decoding executes |
| Restricted host boundary/installer controls | 31 pass in each normal/optimized mode; full host workload is not run |

The nine video skips explicitly report unavailable read-only ffmpeg/ffprobe. They
are a coverage gap, not nine accepted successful cases. Initial admin cases also
failed before execution because isolated HOME had no browser; rerunning with the
explicit existing read-only Playwright cache passes all 12. The image smoke's
first external harness incorrectly expected Next to enlarge a 2px source to
64px; the corrected bound checks the actual unchanged 2px decode. Its earlier
failure remains diagnostic and is not an application regression.

The author gate includes clean npm ci with scripts/native optional dependencies,
npm ls --all, dependency/tooling/runtime controls, TypeScript, lint, full Jest,
production build, real CPU q8 model loading/inference, ZIP extraction and actual
SVG/PNG/WebP decode through both Sharp callers. The fixed public model revision
remains `751bff37182d3f1213fa05d7196b954e230abad9`; Article 142 remains first for
the presidential-term query and the measured native shipped-index cosine is
0.9992964762462274. Production embeddings are never rewritten.

RED/GREEN controls retain the same inputs: cross-realm redirect credentials leak
on 1.16.1 and are stripped on 1.16.2; glob 13 reads 21 directories after the abort
point versus one initial read on 14; the owned truncated PDF times out in a
three-second child on 6.21.2 and refuses promptly on 6.21.4. The PDF child runs
both normally and with true `-O`. Existing optimized auth guards are also run.
The new installer ordering fixture is observed RED before its repair, then GREEN
in normal/optimized modes. Entire-file validation still refuses a malformed later
row before the pip bootstrap; the profile has one authoritative pip pin. Node 24's default reporter exposed an inherited runtime-isolation fixture failure;
its child now explicitly selects TAP and retains all five-case/pass/fail and
source-byte-isolation assertions. The pre-fix failure is preserved.

Early setup failures remain evidence: Python's scratch mount was non-executable
for native wheels; executable owned storage fixes that harness. A SQLite-memory
URL was incompatible with the unchanged engine pool arguments; inert refused
PostgreSQL configuration fixes that harness without connecting to a database.
One successful early build observed newly staged test inputs during execution;
it is diagnostic, superseded by stable final build/browser runs. Neither setup
failure nor source-changing run is counted as acceptance.

No native x86 restricted host workload/capacity qualification, Windows, GPU,
all-browser-engine, current deployed OS/binary census or full repository/hosted CI
acceptance is claimed. The worker fixture's pinned historical Python 3.12.15 base
needs separate verified refresh and unchanged native x86 confinement/capacity
qualification before renewed use. Package-clean does not qualify that image.
Backend and ETL ranges can resolve differently in the future. Read-only hosting
settings are not a new deployed package census; no app deployment occurs here.

## Review, release and rollback

Two independent executable Spec and Standards reviews precede commits/PRs. Draft
PRs remain for owner review; no paid review is requested. Vercel configuration
explicitly excludes `dependabot/**` and this lane's `codex/dependency-security-*`
branches. Read-only settings show Copilot automatic/push/draft review OFF, no
CodeRabbit installation, Render auto-deploy/PR previews OFF, CI/deploy workflows
still disabled, and auto-merge false. Ingestion and its admitted SHA are unchanged.

Rollback is a reviewed revert of the remediation commit and a clean npm ci/fresh
Python environment or rebuild of the previously qualified image. No migration,
asset regeneration or live data undo is required. Reverting reintroduces the
recorded advisories; retain the source/worker/media/publishing holds until an
accepted replacement is available. The separate weekly bot change is independently
revertible. Publishing, uploads, financial generation, native financial source
admission and production worker/supervisor/admin-consumer execution stay OFF.

## Rebase integration — 31 October 2026

The separately owned readiness PR 864 was merged while this lane was validating.
This remediation is rebased onto `ce352b7d61d9b87ee47b0408f2377ea5618a9c34`.
All seven authoritative dependency files are byte-identical before/after the
rebase. Upstream adds seven Jest cases and two admin browser cases; the original
2,897/12-case snapshots above remain attributed to the original base. The final
integrated expected inventory is 2,904 passing Jest cases plus the same one
pending, and 14 admin browser cases. Fresh execution and exact head binding are
reported in the PR delivery. No readiness/source-release branch was modified by
this lane, and no new source or worker opt-in was enabled.
