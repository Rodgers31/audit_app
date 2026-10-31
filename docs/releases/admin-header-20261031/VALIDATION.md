# Admin header ownership — 31 October 2026

The authenticated production admin navigation was covered by the fixed public
site header. The repair gives `/admin` and `/status` route families their guarded
admin navigation alone. The complete public navigation subtree unmounts on private
entry, which also retires its menus and body-scroll effects. Public-site exit,
Account (including the existing public account/sign-out menu) and theme controls
remain reachable. No fixed offset or competing z-index is added.

## Reproduction and production parity

Native Chrome reproduced the issue read-only at `https://www.auditgava.com/admin`.
Its DOM assets identify **dpl_2viCQgG8YyEmPNx9HLUhDxdmxSyU**. The public fixed
header occupies y=0–65 with z-index 50; admin navigation occupies y=12–56.
GitHub's successful production deployment 7438963243 points to frontend merge
`b7eadcb3dde3b7e5236222b8b981b9b0f3786510` (#853). All six relevant shell,
layout and status files are byte-identical at that release and fresh base
`33999e215fe7a1a776685615c832dad4793acd19`; [source-parity.json](source-parity.json)
records their hashes. This establishes relevant source parity, not complete
production environment equivalence.

The actual-root regression was executed before the product repair. It failed
because the Social link's center hit the covering public header, after asserting
the private overview heading. [RED receipt](regression-red.txt) and
[before screenshot](before-desktop.png) preserve that failure. An initial fixture
module-loading error was retained externally and is not counted as RED.

The final identical behavioral assertion passes in the real production build:
[GREEN receipt](regression-green.txt), [desktop](after-desktop.png),
[expanded phone menu](after-phone-expanded.png). The eight-case suite includes
four widths (1728/768/375/320), private route entries, middleware refusal for
anonymous/editor users, and explicit negative controls for its reachability
assertion. It uses the actual RootLayout, middleware, AuthProvider, layouts,
Navigation, status page and compiled product CSS, with inert loopback auth/profile
HTTP transport and explicitly closed sample API reads. There are no product
module aliases or root-layout replacements.

## Why earlier checks missed it

`browser-fixtures/admin-redesign/serve.mjs` generated a replacement root layout.
Its `Harness.tsx` built its own providers and main element without the real root
Navigation. Those component screenshots could not reveal this composition defect.
The earlier validation record now carries that correction and the preview
launcher names the missing release check. Unit/JSDOM tests do not establish
painting or pointer reachability. Existing historical browser cohorts are not
claimed to be a currently passing admin release gate. CI/CD and Docker deployment
workflows remain `disabled_manually`; an old document's claim that all gates run
does not establish that they ran for this release.

**Mandatory local admin UI release gate**, from a clean checkout with the locked
dependencies and supported Node 24.22.1 or later stable 24.x:

```sh
cd frontend
npm run test:admin-shell
```

Run it in addition to the frontend tests, lint, type check, and any component
previews for every admin UI release. It builds and starts the actual application
on loopback 3137 with the owned inert transport on 8137; it refuses ambient env
files, pins public/internal API and Supabase targets to loopback, refuses server
reuse, and fails when prerequisites or the requested case inventory are absent.
Do not replace this gate with the component preview. No hosted workflow was
enabled or rerun by this change.

## Executed validation and bounded adjacent review

- Final actual-root production-build browser gate: **8/8 pass**, no retries.
- Full frontend Jest: **214 suites, 2,869 passes, one pre-existing skip**.
- TypeScript: zero errors. Full lint: zero warnings/errors.
- Independent [Spec review](SPEC.md): **54 browser controls**, plus 45 existing
  auth/lifecycle cases. Eight private route entries at five widths, every task
  link hit-tested, current-task identity, client/public/status/Back transitions,
  similarly prefixed public routes, standalone callbacks, pending/denied auth,
  theme persistence and actual inert sign-out.
- Independent [Standards review](STANDARDS.md): **11 browser/auth scenario
  groups**, eight widths including the 600/601 breakpoint, three reflow routes,
  six reachability controls, five fixture-config controls and three runner
  failure controls. Browser data APIs deliberately return 503 to exercise the
  unavailable-data shell.
- Native isolated Chrome was set to **200% in the browser menu**, then used to
  navigate Overview → Social → System status. The admin links remained visible
  and usable, with no covering public header. Zoom was reset and the owned test
  window closed. This complements the independently labeled effective-width
  reflow tests; neither is silently substituted for the other.

The adjacent review found no additional confirmed shipped defect within those
shell interactions. Standards did find a false pass in the new test helper:
Playwright considered an opacity-zero link visible. Root independently reproduced
it, added ancestor-opacity checks and a permanent negative control, and reran
it GREEN. [Harness RED](harness-red.txt) and [GREEN](harness-green.txt) retain the
executed dispositions. Committed receipt copies remove ANSI escapes and trailing
spaces; original raw logs remain in external evidence. This finding concerns acceptance instrumentation, not a
claimed existing production transparency bug.

The same ownership boundary covers every descendant of `/admin` and `/status`,
including separate status ownership and nested social, ingestion, user and command
routes. Similarly prefixed public paths retain the public header. Standalone
OAuth callback route handlers still return their own HTML and do not enter this
React shell.

## Release status and limits

This is a frontend-only repair with test/validation documentation. No backend,
source-acquisition, data, financial-generation, schema, worker or activation
configuration changes are included. The dirty primary checkout, original chat's
worktree and shared containers were preserved. Publishing, uploads, workers and
financial generation remain held; no production writes were performed.

Production still serves the old frontend artifact above. A merged SHA and a
separately admitted frontend deployment must be recorded before claiming the
production problem is fixed. Recheck actual production private/public navigation
and protected states after deployment while preserving all activation holds.
Rollback is the previous immutable frontend artifact; there is no data rollback.

Chromium only. Inert local auth and populated/error API responses verify shell
behavior, not real external authentication, financial figures, backend operations,
successful mutations, long-data tables, every inner form, all public pages,
screen-reader announcements or WCAG conformance. External fonts/media were blocked
in the browser matrices, covering fallback-font behavior. These results do not
certify the entire application. Independent scripts, complete raw receipts,
setup failures and case inventories are retained in this chat's external
`admin-header/spec-review` and `admin-header/standards-review` evidence directories.
