# Independent backend review for #866/#867

Scoped deployment review: no new confirmed blocker identified in the combined
backend application at `dfc0ea9e3a448ce5e281e15693c56477b280c1a8`. The Claude
public-disclosure repairs are executable and effective. This is not a blanket
claim of vulnerability freedom or complete ingestion egress protection.

Source inspection covered authentication/authorization, user ownership, mounted
write-route admission, public projections/errors, input and download bounds,
file access and listing-selected outbound requests. The review used
`security-audit`, `audit-api-fastapi` and independent adversarial execution.
No application/worktree mutation or production/provider request was made by
this reviewer. Live configuration below comes from the coordinator's explicitly
safe readback, not from an independent production probe by this reviewer.

## Executed coverage

The final bounded sandbox runs pass in normal Python and real `python -O`, with
zero final failures, errors or skips:

| Selection | Application cases per mode |
| --- | ---: |
| HTTP public disclosure, JWT/JWKS, auth/ownership, mounted writes, newsletter and proxy chain | 156 |
| Actual PostgreSQL browser-role privilege repair | 44 |
| Actual PostgreSQL schema/RLS boundaries | 10 |
| Streamed PDF/download bounds | 8 |
| Controlled listing selection traces | 4 |
| Modelled-file reference graph controls, scoped exported backend/ETL view | 37 |
| **Application total** | **259** |

One additional OS-sandbox control case passes per mode, so the complete final
execution count is 260 per mode. The 37 reference-graph checks are explicitly
scoped to the exported backend/ETL source view, not coverage of every repository
surface. Three listing traces intentionally establish the conditional behavior
described below; their passing result is not an assertion of egress clearance.

The 44 browser-privilege cases replay actual migration/helper bodies and execute
real role/permission/DDL/DML refusal paths in isolated PostgreSQL17. The ten older
schema/RLS cases execute the original test assertions with only their self-Docker
fixture replaced by an owned isolated-loopback transport. No Docker socket is
exposed to target code. The replacement preserves migration/grant/seed SQL and
the original readiness wait. These are local behavior proofs, not fresh proof of
an external Supabase project's installed grants or settings.

The disclosure RED replay replaces only `backend/main.py` in a private source
view with its `9d35197` blob, using the same current runtime/tests. It reproduces
11 failures out of14, with zero setup errors/skips. Current code passes all14.
It confirms that server paths/private diagnostic text/admin queue contents no
longer cross those public HTTP boundaries while public DTO fields/statuses and
authorized admin details remain useful.

The first private schema transport wrapper omitted the original fixture's
readiness wait and hit ten local connection-refused setup errors. Those outputs
are retained. Restoring the bounded readiness wait produced clean runs on fresh
owned clusters; no product edit or deselection was used to obtain a pass.

## Classified source leads

No authentication/authorization bypass was found in the inspected and executed
boundaries. JWT verification selects trusted algorithms/keys, profile roles are
read server-side and fail closed, and actual browser roles cannot change their
authorization, truncate protected tables or invoke internal helpers. Two owned
users cannot read/delete/mark the other user's watchlist/alerts.

The remaining `str(exception)` patterns raised by the coordinator are not new
public data leaks in these call chains:

- `main.py:7601` is a private ETL helper result. The repaired public health
  projection no longer publishes the administrative job map.
- `main.py:7970` is behind `require_admin`; its discovery import wrapper raises
  literal deployment guidance rather than arbitrary library/database text.
- JWT exceptions describe caller-supplied malformed/unverifiable tokens or
  validation of public signing keys. Provider transport failures have generic
  503 responses. No secret-bearing database/provider exception was shown to
  cross these public boundaries.
- Money-flow parsing errors describe invalid caller fiscal-year input, while
  signed cache-error details remain behind signature verification.

Public `docs/resolve` uses its URL only to find a record in an existing manifest;
it does not fetch that request parameter or open a caller-selected local file.
Server paths are no longer projected. Storage keys for social media are generated
from server-owned identities; original filenames are metadata. Media activation
and full native binary qualification are outside this review and remain held.

## Existing ingestion trust assumption and open hardening boundary

No anonymous URL-control/SSRF attack path has been confirmed. Operator URL
settings are trusted configuration; the conditional behavior demonstrated here
requires control of the configured upstream listing/JSON response or its
redirect chain. This is an existing ingestion trust assumption and open
hardening boundary, not a newly approved security exception or owner-accepted
risk.

The concrete call chain exists:

1. `national_budget.fetch_national_budget_payload` obtains configured
   `cob_birr_page_url` HTML.
2. `discover_latest_annual_ng_birr` and shared
   `cob_discovery.discover_latest_cob_pdf_url` select matching absolute hrefs
   without a destination-host policy.
3. Annual/latest-report helpers pass those URLs into `get_or_download_pdf` and
   `SeedingHttpClient` before financial/source authority validation.
4. County WP JSON discovery similarly HEADs qualifying `item.source_url`, then
   downloads the selected candidate; county HTML and Treasury BROP paths also
   rely on publisher-selected references.

Three controlled cases execute selection plus an actual client request through
`httpx.MockTransport` for a loopback/other-host destination. No real socket or
external endpoint is contacted. Merely validating a document after download
does not establish pre-request egress safety.

The coordinator's actual safe Render readback at deployed
`8c4b5dee73bfd333c43d9caab78adbcde8232b34` reports:

- `live_pdf_fetch_enabled`, `counties_budget_prefer_live_source` and
  `http_follow_redirects` are true.
- The five projected source settings use HTTPS and official `cob.go.ke` or
  `www.treasury.go.ke`, with no userinfo. Full URL/query values were withheld;
  only hostname/scheme/booleans/digests are supplied.
- `etl.kenya_pipeline` is absent, so the legacy web-specific admin discovery
  path refuses before instantiating a pipeline.
- The twelve inspected runtime ceilings are off/unset and no background worker
  is observed. Publishing, uploads, workers and financial generation remain off.

Separately, the coordinator reports ordinary GitHub ingestion remains enabled
and its admitted SHA is that deployed release. **Finance/source-admission OFF
does not stop its listing fetches or ordinary source writes.** Render settings
are not a complete readback of the separate GitHub runner's effective settings.
An observed official source registry is evidence of previous choices, not proof
of all future listing/redirect/DNS destinations.

This open boundary does not negate the dependency/disclosure repair or establish
a new anonymous deployment blocker. It must remain visible under #802/launch
review; this receipt makes no full ingestion egress guarantee.

The smallest useful policy is to enforce HTTPS, exact publisher/approved alias
host, no userinfo and approved port **before** initial listing requests, selected
URL HEAD/GET requests, and every redirect hop. Keep relative same-publisher links
and required WPDM query strings. Review legitimate CDN hosts explicitly rather
than allowing arbitrary host changes. Checking final `response.url` is too late.
This touches county JSON/HTML, national annual/latest-report and Treasury BROP
discovery, so known redirect/CDN compatibility needs qualification while parser
and financial results stay unchanged. Full public-address validation/peer
pinning provides a stronger DNS/private-resolution guarantee and is a separate
transport concern, not an assurance furnished by the smaller URL policy.

## Isolation, evidence and limits

Execution used cached runtime/image dependencies and a tracked-only source view
with no `.git`, untracked `.env`, credentials or host home mounted. Target code
ran as UID65534 with empty allowlisted environment, read-only source/toolchain/
root, no external network, disabled shared-memory mount, read-only message-queue
mount and capped tmpfs scratch, CPU, memory, processes, file size and wall time.
The final OS control test verifies the enforced identity, limits and failed
writes outside scratch. Trusted supervisors wait for all target processes to
terminate, then promote only bounded, regular, single-link artifacts through
no-follow retained directory descriptors. Retained output directories are never
mounted into the sandbox.

All owned PostgreSQL containers were recreated for independent test groups and
removed afterward. Shared development/production resources were untouched. No
paid model/tool/reviewer/check, hosted CI run, package fetch or new service was
used. Source pins, exact commands, safe environment values, image/profile,
full logs/XML and failed fixture history are retained alongside this report.

This is a scoped application review, not a live penetration test, exhaustive
backend suite, external identity-policy audit, native media-binary qualification
or capacity/denial-of-service benchmark. It does not claim the rest of the
system or all future dependency versions are vulnerability-free.


Public curation note: the complete execution commands, logs and XML referenced
in the original independent report remain in the private coordinator packet.
This public packet contains the sealed summary and the production configuration
projection under a relative filename; it does not claim that every private
fixture/log is published alongside this copy.
